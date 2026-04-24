import calendar
import unicodedata
from copy import deepcopy
from datetime import timedelta

from lxml import etree
from markupsafe import Markup, escape

from odoo import SUPERUSER_ID, api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    CCP_MULTIPLIER = 1.362
    SK_PUBLIC_HOLIDAY_NAMES = {
        "den vzniku slovenskej republiky",
        "zjavenie pana",
        "velky piatok",
        "velkonocny pondelok",
        "sviatok prace",
        "den vitazstva nad fasizmom",
        "sviatok svateho cyrila a svateho metoda",
        "vyrocie slovenskeho narodneho povstania",
        "den ustavy slovenskej republiky",
        "sedembolestna panna maria",
        "sviatok vsetkych svatych",
        "den boja za slobodu a demokraciu",
        "stedry den",
        "prvy sviatok vianocny",
        "druhy sviatok vianocny",
    }

    _PAYROLL_CLEANUP_XMLID = "tenenet_projects.view_hr_employee_form_tenenet_payroll_cleanup_optional"
    _PAYROLL_CLEANUP_ARCH = """
        <data>
            <xpath expr="//button[@icon='fa-dollar']" position="replace"/>
            <xpath expr="//page[@name='salary_attachment']" position="replace"/>
            <xpath expr="//page[@name='personal_information']//field[@name='lang']" position="replace"/>
        </data>
    """

    tenenet_number = fields.Integer(string="Interné číslo")
    title_academic = fields.Char(string="Titul")
    first_name = fields.Char(string="Krstné meno", translate=False)
    last_name = fields.Char(string="Priezvisko", translate=False)
    tenenet_list_name = fields.Char(
        string="Zamestnanec",
        compute="_compute_tenenet_list_name",
        store=True,
    )
    tenenet_list_first_name = fields.Char(
        string="Meno",
        compute="_compute_tenenet_list_name_parts",
        store=True,
    )
    tenenet_list_last_name = fields.Char(
        string="Priezvisko",
        compute="_compute_tenenet_list_name_parts",
        store=True,
    )
    position = fields.Char(string="Pozícia", translate=False)
    contract_position = fields.Char(string="Pozícia podľa pracovnej zmluvy", translate=False)
    organizational_unit_id = fields.Many2one(
        "tenenet.organizational.unit",
        string="Organizačná zložka",
        ondelete="restrict",
        default=lambda self: self.env.ref(
            "tenenet_projects.tenenet_organizational_unit_tenenet_oz",
            raise_if_not_found=False,
        ),
    )
    lang = fields.Selection(
        selection=lambda self: self.env["res.lang"].get_installed(),
        default=lambda self: self._tenenet_default_employee_lang(),
        groups="hr.group_hr_user",
    )
    position_catalog_id = fields.Many2one(
        "hr.job",
        string="Katalóg pozície",
        ondelete="set null",
    )
    additional_job_ids = fields.Many2many(
        "hr.job",
        "hr_employee_additional_job_rel",
        "employee_id",
        "job_id",
        string="Vedľajšie pozície",
    )
    main_site_id = fields.Many2one(
        "tenenet.project.site",
        string="Hlavné miesto práce",
        ondelete="set null",
        domain=[("site_type", "in", ["prevadzka", "centrum"])],
    )
    secondary_site_ids = fields.Many2many(
        "tenenet.project.site",
        "hr_employee_secondary_site_rel",
        "employee_id",
        "site_id",
        string="Vedľajšie miesta práce",
        domain=[("site_type", "in", ["prevadzka", "centrum"])],
    )
    main_site_address_display = fields.Char(
        string="Adresa pracoviska",
        related="main_site_id.address_display",
        readonly=True,
        store=True,
    )
    all_site_names = fields.Char(
        string="Všetky miesta práce",
        compute="_compute_all_site_names",
        store=True,
    )
    all_job_names = fields.Char(
        string="Všetky pozície",
        compute="_compute_all_job_names",
        store=True,
    )
    bio = fields.Html(string="Bio", sanitize=True)
    evaluation_ids = fields.One2many(
        "tenenet.employee.evaluation",
        "employee_id",
        string="Ročné hodnotenia",
    )
    experience_years_total = fields.Float(
        string="Počet rokov praxe",
        digits=(10, 2),
        default=0.0,
    )
    salary_currency_id = fields.Many2one(
        "res.currency",
        string="Mena mzdy",
        related="company_id.currency_id",
        readonly=True,
    )

    @api.model
    def _tenenet_default_employee_lang(self):
        installed_codes = {code for code, _name in self.env["res.lang"].get_installed()}
        return "sk_SK" if "sk_SK" in installed_codes else self.env.lang

    @api.model
    def _tenenet_default_user_lang(self):
        installed_codes = {code for code, _name in self.env["res.lang"].get_installed()}
        return "sk_SK" if "sk_SK" in installed_codes else self.env.lang

    def action_create_user(self):
        action = super().action_create_user()
        action_context = dict(action.get("context", {}))
        action_context.setdefault("default_lang", self._tenenet_default_user_lang())
        action["context"] = action_context
        return action

    monthly_gross_salary_target = fields.Monetary(
        string="Mesačný cieľ CCP",
        currency_field="salary_currency_id",
        help="Cieľová mesačná celková cena práce používaná pre informáciu a dorovnanie do Admin TENENET.",
    )
    monthly_gross_salary_target_hm = fields.Monetary(
        string="Mesačný cieľ HM (brutto)",
        currency_field="salary_currency_id",
        compute="_compute_monthly_gross_salary_target_hm",
        help="Informatívna hrubá mzda odvodená z mesačného cieľa CCP.",
    )
    current_month_effective_workday_count = fields.Integer(
        string="Aktuálny mesiac - pracovné dni po sviatkoch",
        compute="_compute_current_month_salary_target_fields",
    )
    current_month_holiday_workday_count = fields.Integer(
        string="Aktuálny mesiac - sviatky v pracovných dňoch",
        compute="_compute_current_month_salary_target_fields",
    )
    current_month_monthly_gross_salary_target = fields.Monetary(
        string="Aktuálny mesiac - efektívny cieľ CCP",
        currency_field="salary_currency_id",
        compute="_compute_current_month_salary_target_fields",
    )
    current_month_monthly_gross_salary_target_hm = fields.Monetary(
        string="Aktuálny mesiac - efektívny cieľ HM (brutto)",
        currency_field="salary_currency_id",
        compute="_compute_current_month_salary_target_fields",
    )
    profile_summary_html = fields.Html(
        string="Súhrn pracovísk a pozícií",
        compute="_compute_profile_summary_html",
        sanitize=False,
    )
    salary_guidance_html = fields.Html(
        string="Mzdové odporúčanie",
        compute="_compute_salary_guidance_html",
        compute_sudo=True,
        sanitize=False,
    )
    education_info = fields.Text(string="Vzdelanie")
    work_hours = fields.Float(
        string="Denný úväzok (hod.)",
        digits=(10, 2),
        compute="_compute_workload_from_ratio",
        store=True,
        readonly=True,
        help="Denný úväzok odvodený z percenta úväzku pri plnom 8-hodinovom dni.",
    )
    monthly_capacity_hours = fields.Float(
        string="Mesačný fond hodín",
        digits=(10, 2),
        compute="_compute_workload_from_ratio",
        store=True,
        help="Orientačný mesačný fond hodín odvodený z percenta úväzku. Pri plnom úväzku je to 160 hodín.",
    )
    work_ratio = fields.Float(
        string="Úväzok (%)",
        digits=(5, 2),
        default=100.0,
        help="Percento pracovnej kapacity zamestnanca. Pri 100 % je mesačný fond 160 hodín.",
    )
    hourly_rate = fields.Float(
        string="Reziduálna hodinová sadzba CCP",
        digits=(10, 2),
        compute="_compute_hourly_rate",
        inverse="_inverse_hourly_rate",
        help=(
            "Dopočítaná hodinová sadzba CCP pre nepokrytú kapacitu: "
            "(mesačný cieľ CCP - projektová CCP) / (mesačný fond - projektové hodiny)."
        ),
    )
    allocation_ids = fields.One2many(
        "tenenet.employee.allocation",
        "employee_id",
        string="Alokácie",
    )
    utilization_ids = fields.One2many(
        "tenenet.utilization",
        "employee_id",
        string="Vyťaženosť",
    )
    pl_line_ids = fields.One2many(
        "tenenet.pl.line",
        "employee_id",
        string="P&L riadky",
    )
    assignment_ids = fields.One2many(
        "tenenet.project.assignment",
        "employee_id",
        string="Priradenia k projektom",
    )
    training_ids = fields.One2many(
        "tenenet.employee.training",
        "employee_id",
        string="Školenia",
    )
    asset_ids = fields.One2many(
        "tenenet.employee.asset",
        "employee_id",
        string="Firemný majetok",
    )
    tenenet_onboarding_ids = fields.One2many(
        "tenenet.onboarding",
        "employee_id",
        string="Onboarding procesy",
    )
    tenenet_onboarding_count = fields.Integer(
        string="Počet onboardingov",
        compute="_compute_tenenet_onboarding_count",
        compute_sudo=True,
    )
    tenenet_onboarding_state = fields.Selection(
        [
            ("not_started", "Nezačatý"),
            ("in_progress", "Prebieha"),
            ("completed", "Dokončený"),
        ],
        string="Stav onboardingu",
        compute="_compute_tenenet_onboarding_state",
        compute_sudo=True,
    )
    asset_currency_id = fields.Many2one(
        "res.currency",
        string="Mena majetku",
        default=lambda self: self.env.ref("base.EUR"),
    )
    asset_total_value = fields.Monetary(
        string="Hodnota majetku spolu (€)",
        currency_field="asset_currency_id",
        compute="_compute_asset_total_value",
        store=True,
    )
    site_key_ids = fields.One2many(
        "tenenet.employee.site.key",
        "employee_id",
        string="Kľúče",
    )
    service_ids = fields.One2many(
        "tenenet.employee.service",
        "employee_id",
        string="Služby",
    )
    weekly_workplace_ids = fields.One2many(
        "tenenet.employee.weekly.workplace",
        "employee_id",
        string="Týždenný rozvrh pracovísk",
    )
    tenenet_weekly_site_domain_ids = fields.Many2many(
        "tenenet.project.site",
        compute="_compute_tenenet_weekly_site_domain_ids",
        string="Povolené pracoviská pre rozvrh",
    )
    tenenet_cost_ids = fields.One2many(
        "tenenet.employee.tenenet.cost",
        "employee_id",
        string="Tenenet náklady",
    )
    service_manager_user_ids = fields.Many2many(
        "res.users",
        string="Správcovia služieb",
        relation="hr_employee_service_manager_rel",
        column1="employee_id",
        column2="user_id",
        compute="_compute_service_manager_user_ids",
        store=True,
        recursive=True,
    )
    tenenet_project_manager_user_ids = fields.Many2many(
        "res.users",
        string="Projektoví manažéri",
        relation="hr_employee_tenenet_project_manager_user_rel",
        column1="employee_id",
        column2="user_id",
        compute="_compute_tenenet_project_manager_user_ids",
        compute_sudo=True,
        store=True,
        help="Používatelia, ktorí sú projektovým manažérom aktívneho projektu zamestnanca.",
    )
    can_manage_services = fields.Boolean(
        string="Môže spravovať služby",
        compute="_compute_can_manage_services",
    )
    tenenet_is_card_owner = fields.Boolean(
        string="Vlastná karta",
        compute="_compute_tenenet_employee_access_flags",
    )
    tenenet_is_employee_higher_up = fields.Boolean(
        string="Nadriadený v hierarchii",
        compute="_compute_tenenet_employee_access_flags",
    )
    tenenet_is_project_manager_viewer = fields.Boolean(
        string="Projektový manažér tejto karty",
        compute="_compute_tenenet_employee_access_flags",
    )
    tenenet_is_hr_card_admin_viewer = fields.Boolean(
        string="HR karta admin náhľad",
        compute="_compute_tenenet_employee_access_flags",
    )
    tenenet_can_edit_self_employee_fields = fields.Boolean(
        string="Môže upraviť vlastné údaje",
        compute="_compute_tenenet_employee_access_flags",
    )
    tenenet_can_request_employee_update = fields.Boolean(
        string="Môže požiadať o aktualizáciu",
        compute="_compute_tenenet_employee_access_flags",
    )
    tenenet_hr_card_role = fields.Selection(
        [
            ("super_admin", "Super admin"),
            ("admin", "Admin"),
            ("project_admin", "Admin projektový"),
            ("none", "Bez role"),
        ],
        string="HR rola",
        compute="_compute_tenenet_hr_card_role_fields",
        compute_sudo=True,
    )
    tenenet_hr_card_access_note = fields.Char(
        string="Rozsah práv HR karty",
        compute="_compute_tenenet_hr_card_role_fields",
        compute_sudo=True,
    )
    tenenet_responsible_user_ids = fields.Many2many(
        "res.users",
        string="TENENET schvaľovatelia",
        compute="_compute_tenenet_responsible_user_ids",
        compute_sudo=True,
    )
    tenenet_allocation_ratio_total = fields.Float(
        string="Projektový úväzok spolu (%)",
        digits=(5, 2),
        compute="_compute_tenenet_assignment_availability",
        store=True,
    )
    tenenet_actual_work_ratio = fields.Float(
        string="Skutočný úväzok (%)",
        digits=(5, 2),
        compute="_compute_tenenet_assignment_availability",
        store=True,
    )
    tenenet_active_assignment_count = fields.Integer(
        string="Počet aktívnych úväzkov",
        compute="_compute_tenenet_assignment_availability",
        store=True,
    )
    tenenet_availability_state = fields.Selection(
        [
            ("free", "Voľný"),
            ("partial", "Čiastočne alokovaný"),
            ("full", "Plne alokovaný"),
            ("overbooked", "Preťažený"),
        ],
        string="Stav dostupnosti",
        compute="_compute_tenenet_assignment_availability",
        store=True,
    )
    tenenet_availability_label = fields.Char(
        string="Dostupnosť",
        compute="_compute_tenenet_assignment_availability",
        store=True,
    )
    tenenet_free_ratio = fields.Float(
        string="Voľná kapacita (%)",
        digits=(5, 2),
        compute="_compute_tenenet_assignment_availability",
        store=True,
    )
    can_view_private_phone = fields.Boolean(
        compute="_compute_can_view_private_phone",
    )

    @api.model
    def _compose_display_name(self, title_academic, first_name, last_name):
        parts = [part.strip() for part in [title_academic, first_name, last_name] if part and part.strip()]
        return " ".join(parts)

    @api.model
    def _compose_legal_name(self, first_name, last_name):
        parts = [part.strip() for part in [first_name, last_name] if part and part.strip()]
        return " ".join(parts)

    @api.model
    def _split_tenenet_list_name_parts(self, name, title_academic=False):
        name = (name or "").strip()
        title = (title_academic or "").strip()
        if title and name.startswith(title):
            name = name[len(title):].strip()
        parts = name.split()
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return " ".join(parts[:-1]), parts[-1]

    @api.depends("first_name", "last_name", "name", "title_academic")
    def _compute_tenenet_list_name(self):
        for employee in self:
            list_name = employee._compose_legal_name(employee.first_name, employee.last_name)
            if not list_name:
                list_name = (employee.name or "").strip()
                title = (employee.title_academic or "").strip()
                if title and list_name.startswith(title):
                    list_name = list_name[len(title):].strip()
            employee.tenenet_list_name = list_name

    @api.depends("first_name", "last_name", "name", "title_academic")
    def _compute_tenenet_list_name_parts(self):
        for employee in self:
            first_name = (employee.first_name or "").strip()
            last_name = (employee.last_name or "").strip()
            if last_name:
                last_name_parts = last_name.split()
                if len(last_name_parts) > 1:
                    first_name = " ".join(
                        part
                        for part in [first_name, " ".join(last_name_parts[:-1])]
                        if part
                    )
                    last_name = last_name_parts[-1]
            elif not first_name:
                first_name, last_name = employee._split_tenenet_list_name_parts(
                    employee.name,
                    employee.title_academic,
                )
            employee.tenenet_list_first_name = first_name
            employee.tenenet_list_last_name = last_name

    @api.model
    def _sync_tenenet_list_name_parts(self):
        employees = self.sudo().with_context(active_test=False).search([])
        self.env.add_to_compute(self._fields["tenenet_list_first_name"], employees)
        self.env.add_to_compute(self._fields["tenenet_list_last_name"], employees)
        employees._recompute_recordset()

    def _get_site_sequence(self):
        self.ensure_one()
        sites = []
        if self.main_site_id:
            sites.append(self.main_site_id)
        for site in self.secondary_site_ids.sorted(lambda rec: ((rec.name or "").lower(), rec.id)):
            if site not in sites:
                sites.append(site)
        return sites

    def _get_job_sequence(self):
        self.ensure_one()
        jobs = self.env["hr.job"]
        if self.job_id:
            jobs |= self.job_id
        for job in self.additional_job_ids.sorted(lambda rec: ((rec.name or "").lower(), rec.id)):
            if job not in jobs:
                jobs |= job
        return jobs

    def action_send_unsigned_assets_for_signature(self):
        self.ensure_one()
        if not self.work_email:
            raise UserError(_("Zamestnanec %s nemá vyplnený pracovný email.", self.name))

        assets = self.asset_ids.filtered(lambda asset: asset.active and not asset.handover_id)
        if not assets:
            raise UserError(_("Zamestnanec nemá žiadny aktívny majetok bez preberacieho protokolu."))

        handover = self.env["tenenet.employee.asset.handover"].create({
            "employee_id": self.id,
            "handover_date": fields.Date.context_today(self),
        })
        assets.write({
            "handover_id": handover.id,
        })
        handover.action_send_for_signature()
        return {
            "type": "ir.actions.act_window",
            "name": _("Preberací protokol"),
            "res_model": "tenenet.employee.asset.handover",
            "res_id": handover.id,
            "view_mode": "form",
            "target": "current",
        }

    def _is_tenenet_admin_management(self):
        self.ensure_one()
        return any(job.is_tenenet_admin_management for job in self._get_job_sequence())

    @api.model
    def _default_organizational_unit(self):
        return self.env.ref("tenenet_projects.tenenet_organizational_unit_tenenet_oz", raise_if_not_found=False)

    def _guess_organizational_unit(self):
        self.ensure_one()
        units = self.env["tenenet.organizational.unit"]
        if self.wage_program_override_id.organizational_unit_id:
            units |= self.wage_program_override_id.organizational_unit_id
        for assignment in self.assignment_ids.filtered(lambda rec: rec.active and rec.state == "active"):
            unit = assignment.program_id.organizational_unit_id or assignment.project_id.reporting_program_id.organizational_unit_id
            if unit:
                units |= unit
        if len(units) == 1:
            return units
        return self._default_organizational_unit()

    @api.model
    def _backfill_organizational_units(self, force=False):
        for employee in self.with_context(active_test=False).search([]):
            if not force and employee.organizational_unit_id:
                continue
            target_unit = employee._guess_organizational_unit()
            if target_unit and employee.organizational_unit_id != target_unit:
                employee.organizational_unit_id = target_unit

    @api.model
    def _prepare_identity_sync_vals(self, vals, record=None):
        identity_keys = {"title_academic", "first_name", "last_name"}
        if not identity_keys.intersection(vals):
            return vals

        title_academic = vals.get("title_academic", record.title_academic if record else False)
        first_name = vals.get("first_name", record.first_name if record else False)
        last_name = vals.get("last_name", record.last_name if record else False)

        display_name = self._compose_display_name(title_academic, first_name, last_name)
        legal_name = self._compose_legal_name(first_name, last_name)

        synced_vals = dict(vals)
        if display_name:
            synced_vals["name"] = display_name
        if legal_name:
            synced_vals["legal_name"] = legal_name
        return synced_vals

    @api.model
    def _sync_tenenet_display_names(self):
        employees = self.sudo().with_context(active_test=False).search([
            "|",
            ("first_name", "!=", False),
            ("last_name", "!=", False),
        ])
        for employee in employees:
            synced_vals = employee._prepare_identity_sync_vals(
                {
                    "title_academic": employee.title_academic,
                    "first_name": employee.first_name,
                    "last_name": employee.last_name,
                },
                employee,
            )
            values = {
                field_name: synced_vals[field_name]
                for field_name in ("name", "legal_name")
                if synced_vals.get(field_name) and employee[field_name] != synced_vals[field_name]
            }
            if values:
                employee.with_context(tenenet_self_write_sudo=True).write(values)

    @api.model
    def _remove_tenenet_employee_search_override(self):
        xmlid = "tenenet_projects.view_employee_filter_tenenet_list_name"
        view = self.env.ref(xmlid, raise_if_not_found=False)
        model_data = self.env["ir.model.data"].sudo().search([
            ("module", "=", "tenenet_projects"),
            ("name", "=", "view_employee_filter_tenenet_list_name"),
        ], limit=1)
        if view:
            view.sudo().unlink()
        if model_data:
            model_data.unlink()

    @api.model
    def _find_or_create_job_position(self, position_name):
        normalized_name = (position_name or "").strip()
        if not normalized_name:
            return self.env["hr.job"]

        job = self.env["hr.job"].search([("name", "=", normalized_name)], limit=1)
        if not job:
            job = self.env["hr.job"].create({"name": normalized_name})
        return job

    @api.model
    def _prepare_position_sync_vals(self, vals, record=None):
        synced_vals = dict(vals)
        if "position_catalog_id" in vals:
            job = self.env["hr.job"].browse(vals["position_catalog_id"]) if vals["position_catalog_id"] else self.env["hr.job"]
            synced_vals["position"] = job.name or False
            synced_vals["job_id"] = job.id or False
            return synced_vals

        if "job_id" in vals:
            job = self.env["hr.job"].browse(vals["job_id"]) if vals["job_id"] else self.env["hr.job"]
            synced_vals["position"] = job.name or False
            synced_vals["position_catalog_id"] = job.id or False
            return synced_vals

        if "position" not in vals:
            return synced_vals

        job = self._find_or_create_job_position(vals.get("position"))
        synced_vals["position"] = job.name or False
        synced_vals["position_catalog_id"] = job.id or False
        synced_vals["job_id"] = job.id or False
        return synced_vals

    @api.model
    def _prepare_private_phone_sync_vals(self, vals, record=None):
        if "mobile_phone" not in vals and "private_phone" not in vals:
            return vals
        synced_vals = dict(vals)
        legacy_mobile = synced_vals.get("mobile_phone", record.mobile_phone if record else False)
        private_phone = synced_vals.get("private_phone", record.private_phone if record else False)
        if legacy_mobile and not private_phone:
            synced_vals["private_phone"] = legacy_mobile
            synced_vals["mobile_phone"] = False
        return synced_vals

    @api.depends("main_site_id", "main_site_id.name", "secondary_site_ids", "secondary_site_ids.name")
    def _compute_all_site_names(self):
        for employee in self:
            employee.all_site_names = ", ".join(site.display_name for site in employee._get_site_sequence())

    @api.depends("main_site_id", "secondary_site_ids")
    def _compute_tenenet_weekly_site_domain_ids(self):
        for employee in self:
            employee.tenenet_weekly_site_domain_ids = employee.main_site_id | employee.secondary_site_ids

    @api.depends("job_id", "job_id.name", "additional_job_ids", "additional_job_ids.name")
    def _compute_all_job_names(self):
        for employee in self:
            employee.all_job_names = ", ".join(job.display_name for job in employee._get_job_sequence())

    @api.depends("main_site_id", "secondary_site_ids", "job_id", "additional_job_ids")
    def _compute_profile_summary_html(self):
        for employee in self:
            sites = employee._get_site_sequence()
            jobs = employee._get_job_sequence()
            site_items = "".join(
                f"<span class='o_tenenet_employee_chip'>{escape(site.display_name)}</span>"
                for site in sites
            ) or "<span class='text-muted'>Nezadané</span>"
            job_items = "".join(
                f"<span class='o_tenenet_employee_chip'>{escape(job.display_name)}</span>"
                for job in jobs
            ) or "<span class='text-muted'>Nezadané</span>"
            employee.profile_summary_html = Markup(
                """
                <div class="o_tenenet_employee_summary_cards">
                    <div class="o_tenenet_employee_summary_card">
                        <div class="o_tenenet_employee_summary_title">Pozície</div>
                        <div class="o_tenenet_employee_chip_row">%s</div>
                    </div>
                    <div class="o_tenenet_employee_summary_card">
                        <div class="o_tenenet_employee_summary_title">Miesta práce</div>
                        <div class="o_tenenet_employee_chip_row">%s</div>
                    </div>
                </div>
                """
            ) % (Markup(job_items), Markup(site_items))

    @api.depends("asset_ids", "asset_ids.cost", "asset_ids.active")
    def _compute_asset_total_value(self):
        for employee in self:
            employee.asset_total_value = sum(employee.asset_ids.filtered("active").mapped("cost"))

    @api.depends("tenenet_onboarding_ids")
    def _compute_tenenet_onboarding_count(self):
        for employee in self:
            employee.tenenet_onboarding_count = self.env["tenenet.onboarding"].sudo().search_count([
                ("employee_id", "=", employee.id),
            ])

    @api.depends("tenenet_onboarding_ids.phase")
    def _compute_tenenet_onboarding_state(self):
        for employee in self:
            onboardings = self.env["tenenet.onboarding"].sudo().search([
                ("employee_id", "=", employee.id),
            ])
            if not onboardings:
                employee.tenenet_onboarding_state = "not_started"
            elif any(o.phase != "done" for o in onboardings):
                employee.tenenet_onboarding_state = "in_progress"
            else:
                employee.tenenet_onboarding_state = "completed"

    def action_open_onboardings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Onboarding procesy"),
            "res_model": "tenenet.onboarding",
            "view_mode": "list,form",
            "domain": [("employee_id", "=", self.id)],
            "context": {"default_employee_id": self.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        synced_vals_list = []
        for vals in vals_list:
            synced_vals = self._prepare_identity_sync_vals(vals)
            synced_vals = self._prepare_position_sync_vals(synced_vals)
            synced_vals = self._prepare_private_phone_sync_vals(synced_vals)
            synced_vals = self._prepare_tenenet_resource_calendar_vals(synced_vals)
            synced_vals = self._prepare_tenenet_responsible_sync_vals(synced_vals)
            synced_vals_list.append(synced_vals)
        records = super().create(synced_vals_list)
        records.mapped("user_id")._tenenet_sync_hr_project_admin_group_membership()
        return records

    @api.model
    def _tenenet_get_hr_card_admin_users(self, company=None):
        groups = self.env.user._tenenet_get_hr_card_groups()
        group_ids = [
            group.id
            for group in (
                groups.get("super_admin"),
                groups.get("admin"),
                groups.get("project_admin"),
                self.env.ref("base.group_system", raise_if_not_found=False),
                self.env.ref("hr.group_hr_manager", raise_if_not_found=False),
            )
            if group
        ]
        domain = [("share", "=", False)]
        if company:
            domain.append(("company_ids", "in", company.id))
        if group_ids:
            domain.append(("group_ids", "in", group_ids))
        users = self.env["res.users"].sudo().search(domain)
        return users.sorted(key=lambda user: (-user._tenenet_get_hr_card_role_level(), (user.name or "").lower(), user.id))

    def _tenenet_get_responsible_user_candidates(self, parent=None, company=None):
        self.ensure_one()
        company = company or self.company_id
        parent = parent if parent is not None else self.parent_id
        users = self.env["res.users"]
        if parent and parent.user_id and (not company or company in parent.user_id.company_ids):
            users |= parent.user_id
        users |= self._tenenet_get_hr_card_admin_users(company=company)
        return users.sorted(
            key=lambda user: (
                user != parent.user_id,
                -user._tenenet_get_hr_card_role_level(),
                (user.name or "").lower(),
                user.id,
            )
        )

    @api.model
    def _tenenet_pick_primary_responsible_user(self, candidates, preferred_user=None):
        preferred_user = preferred_user if preferred_user in candidates else self.env["res.users"]
        return preferred_user[:1] or candidates[:1]

    @api.model
    def _tenenet_get_calendar_source(self, company=None):
        company = company or self.env.company
        return (
            company.resource_calendar_id
            or self.env.ref("resource.resource_calendar_std", raise_if_not_found=False)
            or self.env["resource.calendar"]
        )

    @api.model
    def _tenenet_get_calendar_target_hours_per_day(self, vals, record=None):
        ratio = vals.get("work_ratio", record.work_ratio if record else 100.0) or 0.0
        company = (
            self.env["res.company"].browse(vals["company_id"])
            if vals.get("company_id")
            else (record.company_id if record else self.env.company)
        )
        source_calendar = self._tenenet_get_calendar_source(company)
        source_hours = source_calendar.hours_per_day or 8.0
        if ratio <= 0.0 or ratio >= 100.0:
            return source_calendar, source_hours
        return source_calendar, round(source_hours * ratio / 100.0, 2)

    @api.model
    def _tenenet_find_or_create_scaled_calendar(self, source_calendar, target_hours_per_day, company=None):
        company = company or self.env.company
        if not source_calendar:
            return self.env["resource.calendar"]
        source_hours = source_calendar.hours_per_day or 8.0
        if target_hours_per_day <= 0.0 or target_hours_per_day >= source_hours:
            return source_calendar

        Calendar = self.env["resource.calendar"].sudo()
        calendar_name = f"{source_calendar.name} ({target_hours_per_day:g}h TENENET)"
        existing = Calendar.search([
            ("company_id", "=", company.id),
            ("hours_per_day", "=", target_hours_per_day),
            ("name", "=", calendar_name),
        ], limit=1)
        if existing:
            return existing

        factor = target_hours_per_day / source_hours if source_hours else 1.0
        attendance_commands = []
        for attendance in source_calendar.attendance_ids.sorted(
            key=lambda rec: (rec.week_type or "", rec.dayofweek or "", rec.hour_from or 0.0, rec.id)
        ):
            duration = max(0.0, (attendance.hour_to or 0.0) - (attendance.hour_from or 0.0))
            attendance_commands.append(fields.Command.create({
                "name": attendance.name,
                "dayofweek": attendance.dayofweek,
                "hour_from": attendance.hour_from,
                "hour_to": round((attendance.hour_from or 0.0) + duration * factor, 4),
                "week_type": attendance.week_type,
                "date_from": attendance.date_from,
                "date_to": attendance.date_to,
                "day_period": attendance.day_period,
                "work_entry_type_id": attendance.work_entry_type_id.id,
                "sequence": attendance.sequence,
            }))

        calendar = Calendar.create({
            "name": calendar_name,
            "company_id": company.id,
            "tz": source_calendar.tz,
            "two_weeks_calendar": source_calendar.two_weeks_calendar,
            "hours_per_day": target_hours_per_day,
            "attendance_ids": attendance_commands,
        })

        leave_model = self.env["resource.calendar.leaves"].sudo()
        for leave in leave_model.search([
            ("calendar_id", "=", source_calendar.id),
            ("resource_id", "=", False),
        ]):
            leave_vals = leave.copy_data()[0]
            leave_vals.update({
                "calendar_id": calendar.id,
                "resource_id": False,
            })
            leave_model.create(leave_vals)
        return calendar

    @api.model
    def _prepare_tenenet_resource_calendar_vals(self, vals, record=None):
        synced_vals = dict(vals)
        if record and not {"work_ratio", "company_id"} & set(vals):
            return synced_vals
        if not record and "resource_calendar_id" in synced_vals and "work_ratio" not in synced_vals:
            return synced_vals

        company = (
            self.env["res.company"].browse(synced_vals["company_id"])
            if synced_vals.get("company_id")
            else (record.company_id if record else self.env.company)
        )
        source_calendar, target_hours_per_day = self._tenenet_get_calendar_target_hours_per_day(
            synced_vals, record=record
        )
        target_calendar = self._tenenet_find_or_create_scaled_calendar(
            source_calendar,
            target_hours_per_day,
            company=company,
        )
        if target_calendar:
            synced_vals["resource_calendar_id"] = target_calendar.id
        return synced_vals

    @api.model
    def _prepare_tenenet_responsible_sync_vals(self, vals, record=None):
        synced_vals = dict(vals)
        if record:
            parent = self.env["hr.employee"].browse(synced_vals["parent_id"]) if synced_vals.get("parent_id") else record.parent_id
            company = self.env["res.company"].browse(synced_vals["company_id"]) if synced_vals.get("company_id") else record.company_id
            candidates = record._tenenet_get_responsible_user_candidates(parent=parent, company=company)
        else:
            parent = self.env["hr.employee"].browse(synced_vals["parent_id"]) if synced_vals.get("parent_id") else self.env["hr.employee"]
            company = self.env["res.company"].browse(synced_vals["company_id"]) if synced_vals.get("company_id") else self.env.company
            candidates = self.env["res.users"]
            if parent and parent.user_id and (not company or company in parent.user_id.company_ids):
                candidates |= parent.user_id
            candidates |= self._tenenet_get_hr_card_admin_users(company=company)
            candidates = candidates.sorted(
                key=lambda user: (
                    user != parent.user_id,
                    -user._tenenet_get_hr_card_role_level(),
                    (user.name or "").lower(),
                    user.id,
                )
            )

        for field_name in ("hr_responsible_id", "expense_manager_id", "leave_manager_id"):
            preferred_user = self.env["res.users"]
            if synced_vals.get(field_name):
                preferred_user = self.env["res.users"].browse(synced_vals[field_name])
            elif record and record[field_name]:
                preferred_user = record[field_name]
            selected_user = self._tenenet_pick_primary_responsible_user(
                candidates,
                preferred_user=preferred_user,
            )
            synced_vals[field_name] = selected_user.id or False
        return synced_vals

    @api.model
    def _tenenet_is_hr_manager(self):
        return self.env.is_superuser() or self.env.user._tenenet_get_hr_card_role_level() >= 2

    @api.model
    def _tenenet_can_view_all_employee_cards(self):
        return self.env.is_superuser() or self.env.user._tenenet_get_hr_card_role_level() >= 1

    @api.model
    def _tenenet_can_edit_all_employee_cards(self):
        return self.env.is_superuser() or self.env.user._tenenet_get_hr_card_role_level() >= 2

    @api.model
    def _tenenet_self_editable_employee_fields(self):
        return {
            "additional_note",
            "bio",
            "resume_line_ids",
            "weekly_workplace_ids",
        }

    @api.model
    def _tenenet_private_card_sudo_read_fields(self):
        return {
            "work_location_name",
            "work_location_type",
        }

    @api.model
    def _tenenet_private_card_access_records(self):
        if self:
            return self.sudo()

        employee_ids = self.env.context.get("tenenet_private_card_access_employee_ids") or []
        if not employee_ids:
            return self.env["hr.employee"]
        return self.env["hr.employee"].sudo().browse(employee_ids).exists()

    @api.model
    def _tenenet_fields_get_with_group_bypass(self, allfields=None, attributes=None):
        result = super().fields_get(allfields=allfields, attributes=attributes)
        requested_fields = allfields or self._fields.keys()
        for field_name in requested_fields:
            if field_name in result:
                continue
            field = self._fields.get(field_name)
            if not field or not self._tenenet_field_requires_group_bypass(field_name):
                continue
            description = field.get_description(self.env, attributes=attributes)
            if "readonly" in description:
                description["readonly"] = description["readonly"] or not self._has_field_access(field, "write")
            result[field_name] = description
        return result

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        if not self._tenenet_should_expand_private_form_view("form"):
            return super().fields_get(allfields=allfields, attributes=attributes)
        return self._tenenet_fields_get_with_group_bypass(allfields=allfields, attributes=attributes)

    def _tenenet_check_employee_write_access(self, vals):
        current_user = self.env.user
        current_user_level = current_user._tenenet_get_hr_card_role_level()
        if self._tenenet_can_edit_all_employee_cards():
            if current_user_level < 3:
                for employee in self:
                    target_level = employee.user_id._tenenet_get_hr_card_role_level() if employee.user_id else 0
                    if target_level >= 3:
                        raise UserError(_("Admin nemôže upravovať HR kartu používateľa so rolou Super admin."))
            return
        if current_user_level >= 1:
            raise UserError(_("Admin projektový môže HR karty iba čítať."))
        requested_fields = set(vals)
        if not requested_fields:
            return
        forbidden_fields = requested_fields - self._tenenet_self_editable_employee_fields()
        for employee in self:
            if employee.user_id == self.env.user and not forbidden_fields:
                continue
            if employee.user_id == self.env.user:
                raise UserError(
                    _(
                        "Vlastnú kartu môžete upravovať iba v povolených poliach: bio, životopis, poznámka a týždenný rozvrh pracovísk."
                    )
                )
            if self.env.user in employee.service_manager_user_ids:
                raise UserError(_("Nadriadený môže kartu zamestnanca iba čítať."))
            raise UserError(_("Nemáte oprávnenie upravovať túto kartu zamestnanca."))

    def write(self, vals):
        previous_users = self.mapped("user_id") if "user_id" in vals else self.env["res.users"]
        if not self.env.context.get("tenenet_self_write_sudo"):
            self._tenenet_check_employee_write_access(vals)
            if (
                not self._tenenet_is_hr_manager()
                and set(vals).issubset(self._tenenet_self_editable_employee_fields())
                and all(employee.user_id == self.env.user for employee in self)
            ):
                return self.sudo().with_context(tenenet_self_write_sudo=True).write(vals)
        if len(self) == 1:
            vals = self._prepare_identity_sync_vals(vals, self)
            vals = self._prepare_position_sync_vals(vals, self)
            vals = self._prepare_private_phone_sync_vals(vals, self)
            vals = self._prepare_tenenet_resource_calendar_vals(vals, self)
            vals = self._prepare_tenenet_responsible_sync_vals(vals, self)
            result = super().write(vals)
            if {"monthly_gross_salary_target", "resource_calendar_id", "work_ratio"} & set(vals):
                periods = set(self.tenenet_cost_ids.mapped("period"))
                for assignment in self.assignment_ids:
                    periods.update(assignment._get_expected_periods())
                    periods.update(assignment.timesheet_ids.mapped("period"))
                if not periods and self.assignment_ids:
                    periods.add(fields.Date.context_today(self).replace(day=1))
                Cost = self.env["tenenet.employee.tenenet.cost"].sudo()
                if periods:
                    for period in periods:
                        Cost._sync_for_employee_period(self.id, period)
                else:
                    self.tenenet_cost_ids._sync_internal_residual_expense()
            if "user_id" in vals:
                (previous_users | self.mapped("user_id"))._tenenet_sync_hr_project_admin_group_membership()
            return result

        for record in self:
            record_vals = record._prepare_identity_sync_vals(vals, record)
            record_vals = record._prepare_position_sync_vals(record_vals, record)
            record_vals = record._prepare_private_phone_sync_vals(record_vals, record)
            record_vals = record._prepare_tenenet_resource_calendar_vals(record_vals, record)
            record_vals = record._prepare_tenenet_responsible_sync_vals(record_vals, record)
            super(HrEmployee, record).write(record_vals)
            if {"monthly_gross_salary_target", "resource_calendar_id", "work_ratio"} & set(vals):
                periods = set(record.tenenet_cost_ids.mapped("period"))
                for assignment in record.assignment_ids:
                    periods.update(assignment._get_expected_periods())
                    periods.update(assignment.timesheet_ids.mapped("period"))
                if not periods and record.assignment_ids:
                    periods.add(fields.Date.context_today(self).replace(day=1))
                Cost = self.env["tenenet.employee.tenenet.cost"].sudo()
                if periods:
                    for period in periods:
                        Cost._sync_for_employee_period(record.id, period)
                else:
                    record.tenenet_cost_ids._sync_internal_residual_expense()
        if "user_id" in vals:
            (previous_users | self.mapped("user_id"))._tenenet_sync_hr_project_admin_group_membership()
        return True

    def _tenenet_can_read_private_card_fields(self):
        if self._tenenet_can_view_all_employee_cards():
            return True
        current_user = self.env.user
        employees = self._tenenet_private_card_access_records()
        if not employees:
            return False
        for employee in employees:
            if employee.user_id == current_user:
                continue
            if current_user in employee.service_manager_user_ids:
                continue
            if employee._tenenet_is_project_manager_employee_user(current_user):
                continue
            return False
        return True

    def _has_field_access(self, field, operation):
        if super()._has_field_access(field, operation):
            return True
        return bool(
            operation == "read"
            and self
            and self._tenenet_can_read_private_card_fields()
            and self._tenenet_field_requires_group_bypass(field.name)
        )

    def _tenenet_field_requires_group_bypass(self, field_name):
        field = self._fields.get(field_name)
        return bool(
            field
            and (
                field_name in self._tenenet_private_card_sudo_read_fields()
                or (field.groups and not self.env.user.has_groups(field.groups))
                or self._tenenet_related_field_requires_group_bypass(field)
                or self._tenenet_computed_field_requires_group_bypass(field)
            )
        )

    def _tenenet_computed_field_requires_group_bypass(self, field):
        if not getattr(field, "compute", None):
            return False

        for depends_field_name in getattr(field, "depends", ()) or ():
            root_field_name = depends_field_name.split(".", 1)[0]
            depends_field = self._fields.get(root_field_name)
            if (
                depends_field
                and depends_field.groups
                and not self.env.user.has_groups(depends_field.groups)
            ):
                return True
        return False

    def _tenenet_related_field_requires_group_bypass(self, field):
        related_path = getattr(field, "related", None)
        if not related_path:
            return False
        if isinstance(related_path, str):
            related_path = related_path.split(".")

        model = self
        for related_field_name in related_path:
            related_field = model._fields.get(related_field_name)
            if not related_field:
                return False
            if related_field.groups and not self.env.user.has_groups(related_field.groups):
                return True
            if getattr(related_field, "comodel_name", None):
                model = self.env[related_field.comodel_name]
            else:
                break
        return False

    def read(self, fields=None, load="_classic_read"):
        requested_fields = list(fields) if fields else None
        read_fields = requested_fields
        inject_additional_note = bool(
            requested_fields
            and "additional_note" in requested_fields
            and not self.env.user.has_group("hr.group_hr_user")
        )
        group_bypass_fields = []
        if (
            requested_fields
            and not self.env.su
            and not self.env.user.has_group("hr.group_hr_user")
            and self._tenenet_can_read_private_card_fields()
        ):
            group_bypass_fields = [
                field_name
                for field_name in requested_fields
                if self._tenenet_field_requires_group_bypass(field_name)
            ]

        fields_to_remove = set(group_bypass_fields)
        if inject_additional_note:
            fields_to_remove.add("additional_note")

        if fields_to_remove:
            read_fields = [
                field
                for field in requested_fields
                if field not in fields_to_remove
            ]
            if not read_fields:
                read_fields = ["id"]

        if inject_additional_note:
            fields_to_remove.add("additional_note")

        values_list = super().read(fields=read_fields, load=load)

        if group_bypass_fields:
            employees = self.sudo().browse([values["id"] for values in values_list])
            sudo_values_by_id = {
                values["id"]: values
                for values in employees.read(group_bypass_fields, load=load)
            }
            for values in values_list:
                values.update({
                    field: sudo_values_by_id.get(values["id"], {}).get(field)
                    for field in group_bypass_fields
                })

        if inject_additional_note and "additional_note" not in group_bypass_fields:
            employees = self.sudo().browse([values["id"] for values in values_list])
            note_by_id = {employee.id: employee.additional_note for employee in employees}
            for values in values_list:
                values["additional_note"] = note_by_id.get(values["id"])

        if fields and "private_phone" not in fields:
            return values_list

        access_map = self._get_private_phone_access_map()
        for values in values_list:
            if not access_map.get(values["id"]):
                values["private_phone"] = False
        return values_list

    def web_read(self, specification):
        if (
            self.env.context.get("tenenet_private_card_web_read_sudo")
            or self.env.su
            or self.env.user.has_group("hr.group_hr_user")
            or not specification
            or not self._tenenet_can_read_private_card_fields()
        ):
            return super().web_read(specification)

        sudo_field_names = [
            field_name
            for field_name in specification
            if self._tenenet_field_requires_group_bypass(field_name)
        ]
        if not sudo_field_names:
            return super().web_read(specification)

        sudo_fields = set(sudo_field_names)
        normal_specification = {
            field_name: field_spec
            for field_name, field_spec in specification.items()
            if field_name not in sudo_fields
        }
        sudo_specification = {
            field_name: specification[field_name]
            for field_name in sudo_field_names
        }
        values_list = super().web_read(normal_specification or {"id": {}})
        sudo_values_by_id = {
            values["id"]: values
            for values in self.sudo()
            .with_context(tenenet_private_card_web_read_sudo=True)
            .web_read(sudo_specification)
        }
        for values in values_list:
            values.update({
                field_name: sudo_values_by_id.get(values["id"], {}).get(field_name)
                for field_name in sudo_field_names
            })
        return values_list

    @api.model
    def _tenenet_private_form_page_names(self):
        return ("personal_information",)

    @api.model
    def _tenenet_should_expand_private_form_view(self, view_type):
        return bool(
            view_type == "form"
            and not self.env.su
            and self.env.user.has_group("base.group_user")
            and not self.env.user.has_group("hr.group_hr_user")
        )

    @api.model
    def _tenenet_prepare_readonly_private_form_page(self, page):
        readonly_mode = not self._tenenet_can_edit_all_employee_cards()
        page.set(
            "invisible",
            "not (tenenet_is_card_owner or tenenet_is_employee_higher_up or tenenet_is_project_manager_viewer or tenenet_is_hr_card_admin_viewer)",
        )

        for node in page.xpath(".//*[@groups]"):
            node.attrib.pop("groups", None)

        if readonly_mode:
            for button in page.xpath(".//button | .//a[@type]"):
                parent = button.getparent()
                if parent is not None:
                    parent.remove(button)

            for arch_node in page.xpath(".//list | .//form | .//kanban"):
                arch_node.attrib.pop("editable", None)
                arch_node.set("create", "False")
                arch_node.set("edit", "False")
                arch_node.set("delete", "False")

            for field_node in page.xpath(".//field"):
                field_node.set("readonly", "1")

        return page

    @api.model
    def _tenenet_merge_view_models(self, current_models, privileged_models):
        merged_models = {
            model: list(field_names)
            for model, field_names in (current_models or {}).items()
        }
        for model, field_names in (privileged_models or {}).items():
            merged_field_names = set(merged_models.get(model, []))
            merged_field_names.update(field_names)
            merged_models[model] = list(merged_field_names)
        return merged_models

    @api.model
    def _tenenet_merge_private_form_pages(self, current_arch, privileged_arch):
        current_root = etree.fromstring(current_arch.encode())
        privileged_root = etree.fromstring(privileged_arch.encode())

        current_notebook = current_root.xpath("//notebook")
        privileged_notebook = privileged_root.xpath("//notebook")
        if not current_notebook or not privileged_notebook:
            return current_arch

        current_notebook = current_notebook[0]
        privileged_notebook = privileged_notebook[0]
        current_pages = {
            page.get("name"): page
            for page in current_notebook.xpath("./page")
            if page.get("name")
        }
        privileged_pages = {
            page.get("name"): page
            for page in privileged_notebook.xpath("./page")
            if page.get("name")
        }
        tenenet_page = next(
            (page for page in current_notebook.xpath("./page") if page.get("string") == "TENENET"),
            None,
        )
        insert_at = current_notebook.index(tenenet_page) if tenenet_page is not None else len(current_notebook)

        for page_name in self._tenenet_private_form_page_names():
            source_page = privileged_pages.get(page_name)
            if source_page is None:
                continue
            page_copy = deepcopy(source_page)
            self._tenenet_prepare_readonly_private_form_page(page_copy)
            current_page = current_pages.get(page_name)
            if current_page is not None:
                current_notebook.replace(current_page, page_copy)
            else:
                current_notebook.insert(insert_at, page_copy)
                insert_at += 1

        return etree.tostring(current_root, encoding="unicode")

    def get_view(self, view_id=None, view_type="form", **options):
        if not self._tenenet_should_expand_private_form_view(view_type):
            return super().get_view(view_id=view_id, view_type=view_type, **options)

        access_employee_ids = tuple(self.ids or self.env.context.get("tenenet_private_card_access_employee_ids") or ())
        result = super(
            HrEmployee,
            self.with_context(tenenet_private_card_access_employee_ids=access_employee_ids),
        ).get_view(view_id=view_id, view_type=view_type, **options)
        privileged_result = super(
            HrEmployee,
            self.with_user(SUPERUSER_ID).with_context(
                tenenet_private_card_access_employee_ids=access_employee_ids,
            ),
        ).get_view(view_id=view_id, view_type=view_type, **options)
        result["arch"] = self._tenenet_merge_private_form_pages(
            result["arch"],
            privileged_result["arch"],
        )
        result["models"] = self._tenenet_merge_view_models(
            result.get("models"),
            privileged_result.get("models"),
        )
        return result

    @api.model
    def _sync_optional_payroll_cleanup_view(self):
        payroll_view = self.env.ref("hr_payroll.payroll_hr_employee_view_form", raise_if_not_found=False)
        model_data = self.env["ir.model.data"].sudo()
        existing = model_data.search([
            ("module", "=", "tenenet_projects"),
            ("name", "=", "view_hr_employee_form_tenenet_payroll_cleanup_optional"),
        ], limit=1)

        if not payroll_view:
            if existing and existing.model == "ir.ui.view":
                self.env["ir.ui.view"].sudo().browse(existing.res_id).unlink()
            return

        vals = {
            "name": "hr.employee.form.tenenet.payroll.cleanup.optional",
            "type": "form",
            "model": "hr.employee",
            "inherit_id": payroll_view.id,
            "priority": 260,
            "arch_base": self._PAYROLL_CLEANUP_ARCH,
        }
        view_model = self.env["ir.ui.view"].sudo()
        if existing and existing.model == "ir.ui.view":
            view_model.browse(existing.res_id).write(vals)
            return

        created_view = view_model.create(vals)
        model_data.create({
            "module": "tenenet_projects",
            "name": "view_hr_employee_form_tenenet_payroll_cleanup_optional",
            "model": "ir.ui.view",
            "res_id": created_view.id,
            "noupdate": True,
        })

    def _register_hook(self):
        result = super()._register_hook()
        try:
            with self.env.cr.savepoint():
                self._sync_optional_payroll_cleanup_view()
        except Exception:
            # Another worker already updated the view; safe to skip.
            pass
        return result

    @api.depends("work_ratio")
    def _compute_workload_from_ratio(self):
        for rec in self:
            ratio = rec.work_ratio or 0.0
            hours_per_day = 8.0 * ratio / 100.0
            rec.work_hours = hours_per_day
            rec.monthly_capacity_hours = 160.0 * ratio / 100.0

    @api.depends("monthly_gross_salary_target")
    def _compute_monthly_gross_salary_target_hm(self):
        for rec in self:
            rec.monthly_gross_salary_target_hm = (rec.monthly_gross_salary_target or 0.0) / self.CCP_MULTIPLIER

    @api.model
    def _get_target_period(self, period=None):
        raw_period = period or self.env.context.get("tenenet_period") or fields.Date.context_today(self)
        return fields.Date.to_date(raw_period).replace(day=1)

    def _get_working_weekdays(self):
        self.ensure_one()
        calendar_record = self.resource_calendar_id
        if not calendar_record:
            return {0, 1, 2, 3, 4}
        weekdays = {
            int(attendance.dayofweek)
            for attendance in calendar_record.attendance_ids
            if attendance.dayofweek not in (False, None)
        }
        return weekdays or {0, 1, 2, 3, 4}

    @api.model
    def _normalize_sk_public_holiday_name(self, name):
        normalized = unicodedata.normalize("NFKD", (name or "").strip().casefold())
        return "".join(char for char in normalized if not unicodedata.combining(char))

    @api.model
    def _is_calendar_leave_public_holiday(self, leave):
        if not leave or leave.resource_id:
            return False
        return self._normalize_sk_public_holiday_name(leave.name) in self.SK_PUBLIC_HOLIDAY_NAMES

    def _get_public_holiday_leaves_for_period(self, period):
        self.ensure_one()
        normalized_period = self._get_target_period(period)
        month_end_day = calendar.monthrange(normalized_period.year, normalized_period.month)[1]
        month_start = normalized_period
        month_end = normalized_period.replace(day=month_end_day)
        leave_model = self.env["resource.calendar.leaves"].sudo()
        domain = [
            ("resource_id", "=", False),
            ("date_from", "<=", fields.Datetime.to_string(month_end + timedelta(days=1))),
            ("date_to", ">=", fields.Datetime.to_string(month_start)),
        ]
        if self.resource_calendar_id:
            domain = ["|", ("calendar_id", "=", False), ("calendar_id", "=", self.resource_calendar_id.id)] + domain
        leaves = leave_model.search(domain)
        return leaves.filtered(self._is_calendar_leave_public_holiday)

    def _get_month_workday_metrics(self, period):
        self.ensure_one()
        normalized_period = self._get_target_period(period)
        month_end_day = calendar.monthrange(normalized_period.year, normalized_period.month)[1]
        working_weekdays = self._get_working_weekdays()
        base_days = {
            normalized_period.replace(day=day)
            for day in range(1, month_end_day + 1)
            if normalized_period.replace(day=day).weekday() in working_weekdays
        }
        holiday_days = set()
        for leave in self._get_public_holiday_leaves_for_period(normalized_period):
            date_from = fields.Datetime.to_datetime(leave.date_from)
            date_to = fields.Datetime.to_datetime(leave.date_to)
            current_day = date_from.date()
            end_day = date_to.date()
            while current_day <= end_day:
                if (
                    current_day.month == normalized_period.month
                    and current_day.year == normalized_period.year
                    and current_day in base_days
                ):
                    holiday_days.add(current_day)
                current_day += timedelta(days=1)
        return {
            "base_workdays": len(base_days),
            "holiday_workdays": len(holiday_days),
            "effective_workdays": max(0, len(base_days) - len(holiday_days)),
        }

    def _get_effective_monthly_gross_salary_target(self, period=None):
        self.ensure_one()
        raw_target = self.monthly_gross_salary_target or 0.0
        if raw_target <= 0.0:
            return 0.0
        metrics = self._get_month_workday_metrics(period)
        base_workdays = metrics["base_workdays"]
        if base_workdays <= 0:
            return 0.0
        return raw_target * (metrics["effective_workdays"] / base_workdays)

    def _get_effective_monthly_gross_salary_target_hm(self, period=None):
        self.ensure_one()
        return self._get_effective_monthly_gross_salary_target(period) / self.CCP_MULTIPLIER

    @api.depends(
        "monthly_gross_salary_target",
        "resource_calendar_id",
        "resource_calendar_id.attendance_ids",
        "resource_calendar_id.leave_ids",
    )
    def _compute_current_month_salary_target_fields(self):
        current_period = self._get_target_period()
        for rec in self:
            metrics = rec._get_month_workday_metrics(current_period)
            rec.current_month_effective_workday_count = metrics["effective_workdays"]
            rec.current_month_holiday_workday_count = metrics["holiday_workdays"]
            rec.current_month_monthly_gross_salary_target = rec._get_effective_monthly_gross_salary_target(current_period)
            rec.current_month_monthly_gross_salary_target_hm = rec._get_effective_monthly_gross_salary_target_hm(current_period)

    @api.model
    def _get_tenenet_hourly_rate_period(self):
        period = self.env.context.get("tenenet_period") or fields.Date.context_today(self)
        return fields.Date.to_date(period).replace(day=1)

    @api.depends(
        "monthly_gross_salary_target",
        "monthly_capacity_hours",
        "assignment_ids.timesheet_ids.period",
        "assignment_ids.timesheet_ids.hours_total",
        "assignment_ids.timesheet_ids.hours_project_total",
        "assignment_ids.timesheet_ids.total_labor_cost",
    )
    @api.depends_context("tenenet_period")
    def _compute_hourly_rate(self):
        Cost = self.env["tenenet.employee.tenenet.cost"].sudo()
        Timesheet = self.env["tenenet.project.timesheet"].sudo()
        period = self._get_tenenet_hourly_rate_period()
        for rec in self:
            if not rec.id:
                rec.hourly_rate = 0.0
                continue
            coverage = Cost._get_employee_month_project_coverage(rec, period)
            timesheets = Timesheet.search([
                ("employee_id", "=", rec.id),
                ("period", "=", period),
                ("project_id.is_tenenet_internal", "=", False),
            ])
            project_hours = sum(timesheets.mapped("hours_total"))
            project_ccp = coverage["total_ccp"]
            effective_target_ccp = rec._get_effective_monthly_gross_salary_target(period)
            remaining_ccp = max(0.0, effective_target_ccp - project_ccp)
            remaining_hours = max(0.0, (rec.monthly_capacity_hours or 0.0) - project_hours)
            rec.hourly_rate = remaining_ccp / remaining_hours if remaining_hours else 0.0

    def _inverse_hourly_rate(self):
        # Kept for compatibility with legacy imports/tests that still write hourly_rate.
        return

    @api.depends("parent_id", "parent_id.user_id", "parent_id.service_manager_user_ids")
    def _compute_service_manager_user_ids(self):
        for rec in self:
            manager_users = self.env["res.users"]
            if rec.parent_id:
                manager_users |= rec.parent_id.user_id
                manager_users |= rec.parent_id.service_manager_user_ids
            rec.service_manager_user_ids = manager_users

    @api.depends(
        "assignment_ids.is_current",
        "assignment_ids.project_id.active",
        "assignment_ids.project_id.project_manager_id",
        "assignment_ids.project_id.project_manager_id.user_id",
    )
    def _compute_tenenet_project_manager_user_ids(self):
        for rec in self:
            current_assignments = rec.assignment_ids.filtered(
                lambda assignment: assignment.is_current
                and assignment.project_id.active
                and assignment.project_id.project_manager_id.user_id
            )
            rec.tenenet_project_manager_user_ids = current_assignments.mapped(
                "project_id.project_manager_id.user_id"
            )

    def _tenenet_is_project_manager_employee_user(self, user=None):
        current_user = user or self.env.user
        self.ensure_one()
        return bool(
            self.sudo().assignment_ids.filtered(
                lambda assignment: assignment.is_current
                and assignment.project_id.active
                and assignment.project_id.project_manager_id.user_id == current_user
            )
        )

    @api.depends_context("uid")
    def _compute_can_manage_services(self):
        is_hr_manager = self._tenenet_can_edit_all_employee_cards()
        for rec in self:
            rec.can_manage_services = bool(is_hr_manager)

    @api.depends(
        "user_id",
        "user_id.group_ids",
        "service_manager_user_ids",
        "assignment_ids.is_current",
        "assignment_ids.project_id.active",
        "assignment_ids.project_id.project_manager_id.user_id",
    )
    @api.depends_context("uid")
    def _compute_tenenet_employee_access_flags(self):
        current_user = self.env.user
        can_edit_all_cards = self._tenenet_can_edit_all_employee_cards()
        can_view_all_cards = self._tenenet_can_view_all_employee_cards()
        for rec in self:
            is_owner = bool(rec.user_id and rec.user_id == current_user)
            is_higher_up = bool(rec.service_manager_user_ids.filtered(lambda user: user == current_user))
            is_project_manager_viewer = rec._tenenet_is_project_manager_employee_user(current_user)
            is_hr_card_admin_viewer = bool(can_view_all_cards)
            rec.tenenet_is_card_owner = is_owner
            rec.tenenet_is_employee_higher_up = is_higher_up
            rec.tenenet_is_project_manager_viewer = is_project_manager_viewer
            rec.tenenet_is_hr_card_admin_viewer = is_hr_card_admin_viewer
            rec.tenenet_can_edit_self_employee_fields = bool(
                can_edit_all_cards or (is_owner and not is_hr_card_admin_viewer)
            )
            rec.tenenet_can_request_employee_update = bool(
                can_edit_all_cards or (is_owner and not is_hr_card_admin_viewer)
            )

    @api.depends("user_id", "user_id.group_ids")
    def _compute_tenenet_hr_card_role_fields(self):
        for rec in self:
            user = rec.user_id
            if not user:
                rec.tenenet_hr_card_role = "none"
                rec.tenenet_hr_card_access_note = "Bez osobitnej HR roly."
                continue
            role_code = user._tenenet_get_hr_card_role_code() or "none"
            rec.tenenet_hr_card_role = role_code
            rec.tenenet_hr_card_access_note = {
                "super_admin": "Vidí a upravuje všetky HR karty.",
                "admin": "Vidí a upravuje všetky HR karty okrem Super admin používateľov.",
                "project_admin": "Vidí všetky HR karty, ale needituje nič.",
                "none": "Bez osobitnej HR roly.",
            }[role_code]

    def _compute_tenenet_responsible_user_ids(self):
        for rec in self:
            rec.tenenet_responsible_user_ids = rec._tenenet_get_responsible_user_candidates()

    @api.depends("parent_id", "parent_id.user_id", "company_id")
    def _compute_expense_manager(self):
        for employee in self:
            parent_user = employee.parent_id.user_id
            previous_parent_user = employee._origin.parent_id.user_id
            preferred_user = (
                employee.expense_manager_id
                if employee.expense_manager_id and employee.expense_manager_id != previous_parent_user
                else parent_user
            )
            candidates = employee._tenenet_get_responsible_user_candidates()
            employee.expense_manager_id = self._tenenet_pick_primary_responsible_user(
                candidates,
                preferred_user=preferred_user,
            )

    @api.depends("parent_id", "parent_id.user_id", "company_id")
    def _compute_leave_manager(self):
        for employee in self:
            parent_user = employee.parent_id.user_id
            previous_parent_user = employee._origin.parent_id.user_id
            preferred_user = (
                employee.leave_manager_id
                if employee.leave_manager_id and employee.leave_manager_id != previous_parent_user
                else parent_user
            )
            candidates = employee._tenenet_get_responsible_user_candidates()
            employee.leave_manager_id = self._tenenet_pick_primary_responsible_user(
                candidates,
                preferred_user=preferred_user,
            )

    def action_tenenet_open_employee_update_request_wizard(self):
        self.ensure_one()
        if not self.tenenet_can_request_employee_update:
            raise UserError(_("Nemáte oprávnenie požiadať o aktualizáciu tejto karty."))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Aktualizovať"),
                "message": _("Táto funkcia je zatiaľ pripravená len ako zástupné tlačidlo."),
                "type": "warning",
                "sticky": False,
            },
        }

    def _get_private_phone_access_map(self, user=None):
        current_user = user or self.env.user
        if current_user._tenenet_get_hr_card_role_level() >= 1 or current_user.has_group("base.group_system"):
            return {employee.id: True for employee in self}

        access_map = {}
        for employee in self:
            access_map[employee.id] = bool(
                employee.user_id == current_user
                or current_user in employee.service_manager_user_ids
                or employee._tenenet_is_project_manager_employee_user(current_user)
            )
        return access_map

    @api.depends(
        "user_id",
        "service_manager_user_ids",
        "assignment_ids.is_current",
        "assignment_ids.project_id.active",
        "assignment_ids.project_id.project_manager_id.user_id",
    )
    @api.depends_context("uid")
    def _compute_can_view_private_phone(self):
        access_map = self._get_private_phone_access_map()
        for employee in self:
            employee.can_view_private_phone = access_map.get(employee.id, False)

    @api.depends(
        "work_ratio",
        "assignment_ids.active",
        "assignment_ids.allocation_ratio",
        "assignment_ids.ratio_month_ids.allocation_ratio",
        "assignment_ids.ratio_month_ids.period",
        "assignment_ids.date_start",
        "assignment_ids.date_end",
        "assignment_ids.is_current",
        "assignment_ids.project_id.date_start",
        "assignment_ids.project_id.date_end",
    )
    def _compute_tenenet_assignment_availability(self):
        current_period = fields.Date.context_today(self).replace(day=1)
        for rec in self:
            active_assignments = rec.assignment_ids.filtered(lambda assignment: assignment.is_current)
            capacity_ratio = rec.work_ratio or 0.0
            total_ratio = sum(
                assignment._get_effective_work_ratio_for_period(current_period)
                for assignment in active_assignments
            )
            rec.tenenet_allocation_ratio_total = total_ratio
            rec.tenenet_actual_work_ratio = total_ratio
            rec.tenenet_active_assignment_count = len(active_assignments)
            rec.tenenet_free_ratio = max(0.0, capacity_ratio - total_ratio)
            if total_ratio <= 0.0:
                rec.tenenet_availability_state = "free"
                rec.tenenet_availability_label = "Voľný"
            elif capacity_ratio > 0.0 and total_ratio < capacity_ratio:
                rec.tenenet_availability_state = "partial"
                rec.tenenet_availability_label = "Čiastočne alokovaný"
            elif total_ratio == capacity_ratio:
                rec.tenenet_availability_state = "full"
                rec.tenenet_availability_label = "Plne alokovaný"
            else:
                rec.tenenet_availability_state = "overbooked"
                rec.tenenet_availability_label = "Preťažený"

    @api.constrains("main_site_id", "secondary_site_ids")
    def _check_work_sites(self):
        allowed_types = {"prevadzka", "centrum"}
        for rec in self:
            if rec.main_site_id and rec.main_site_id.site_type not in allowed_types:
                raise ValidationError("Hlavné miesto práce môže byť len prevádzka alebo centrum.")
            invalid_secondary = rec.secondary_site_ids.filtered(lambda site: site.site_type not in allowed_types)
            if invalid_secondary:
                raise ValidationError("Vedľajšie miesta práce môžu byť len prevádzky alebo centrá.")
            if rec.main_site_id and rec.main_site_id in rec.secondary_site_ids:
                raise ValidationError("Hlavné miesto práce nesmie byť zároveň medzi vedľajšími miestami.")

    @api.constrains("active", "organizational_unit_id")
    def _check_organizational_unit(self):
        for rec in self:
            if rec.active and not rec.organizational_unit_id:
                raise ValidationError("Aktívny zamestnanec musí mať nastavenú organizačnú zložku.")
