from markupsafe import Markup, escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    CCP_MULTIPLIER = 1.362

    _PAYROLL_CLEANUP_XMLID = "tenenet_projects.view_hr_employee_form_tenenet_payroll_cleanup_optional"
    _PAYROLL_CLEANUP_ARCH = """
        <data>
            <xpath expr="//button[@icon='fa-dollar']" position="replace"/>
            <xpath expr="//page[@name='salary_attachment']" position="replace"/>
        </data>
    """

    tenenet_number = fields.Integer(string="Interné číslo")
    title_academic = fields.Char(string="Titul")
    first_name = fields.Char(string="Krstné meno", translate=False)
    last_name = fields.Char(string="Priezvisko", translate=False)
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
    bio = fields.Text(string="Bio")
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
    profile_summary_html = fields.Html(
        string="Súhrn pracovísk a pozícií",
        compute="_compute_profile_summary_html",
        sanitize=False,
    )
    salary_guidance_html = fields.Html(
        string="Mzdové odporúčanie",
        compute="_compute_salary_guidance_html",
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
    )
    tenenet_onboarding_state = fields.Selection(
        [
            ("not_started", "Nezačatý"),
            ("in_progress", "Prebieha"),
            ("completed", "Dokončený"),
        ],
        string="Stav onboardingu",
        compute="_compute_tenenet_onboarding_state",
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
    can_manage_services = fields.Boolean(
        string="Môže spravovať služby",
        compute="_compute_can_manage_services",
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
        jobs = []
        if self.job_id:
            jobs.append(self.job_id)
        for job in self.additional_job_ids.sorted(lambda rec: ((rec.name or "").lower(), rec.id)):
            if job not in jobs:
                jobs.append(job)
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
            employee.tenenet_onboarding_count = len(employee.tenenet_onboarding_ids)

    @api.depends("tenenet_onboarding_ids.phase")
    def _compute_tenenet_onboarding_state(self):
        for employee in self:
            onboardings = employee.tenenet_onboarding_ids
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
            synced_vals_list.append(synced_vals)
        return super().create(synced_vals_list)

    def write(self, vals):
        if len(self) == 1:
            vals = self._prepare_identity_sync_vals(vals, self)
            vals = self._prepare_position_sync_vals(vals, self)
            vals = self._prepare_private_phone_sync_vals(vals, self)
            result = super().write(vals)
            if "monthly_gross_salary_target" in vals:
                self.tenenet_cost_ids._sync_internal_residual_expense()
            return result

        for record in self:
            record_vals = record._prepare_identity_sync_vals(vals, record)
            record_vals = record._prepare_position_sync_vals(record_vals, record)
            record_vals = record._prepare_private_phone_sync_vals(record_vals, record)
            super(HrEmployee, record).write(record_vals)
            if "monthly_gross_salary_target" in vals:
                record.tenenet_cost_ids._sync_internal_residual_expense()
        return True

    def read(self, fields=None, load="_classic_read"):
        values_list = super().read(fields=fields, load=load)
        if fields and "private_phone" not in fields:
            return values_list

        access_map = self._get_private_phone_access_map()
        for values in values_list:
            if not access_map.get(values["id"]):
                values["private_phone"] = False
        return values_list

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
        Timesheet = self.env["tenenet.project.timesheet"].sudo()
        period = self._get_tenenet_hourly_rate_period()
        for rec in self:
            if not rec.id:
                rec.hourly_rate = 0.0
                continue
            timesheets = Timesheet.search([
                ("employee_id", "=", rec.id),
                ("period", "=", period),
                ("project_id.is_tenenet_internal", "=", False),
            ])
            project_hours = sum(timesheets.mapped("hours_total"))
            project_ccp = sum(timesheets.mapped("total_labor_cost"))
            remaining_ccp = max(0.0, (rec.monthly_gross_salary_target or 0.0) - project_ccp)
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

    def _compute_can_manage_services(self):
        current_user = self.env.user
        is_hr_manager = current_user.has_group("hr.group_hr_manager")
        for rec in self:
            rec.can_manage_services = bool(
                is_hr_manager
                or rec.service_manager_user_ids.filtered(lambda user: user == current_user)
            )

    def _get_private_phone_access_map(self, user=None):
        current_user = user or self.env.user
        if current_user.has_group("hr.group_hr_manager") or current_user.has_group("base.group_system"):
            return {employee.id: True for employee in self}

        access_map = {}
        for employee in self:
            access_map[employee.id] = bool(
                employee.user_id == current_user
                or current_user in employee.service_manager_user_ids
            )
        return access_map

    @api.depends("user_id", "service_manager_user_ids")
    @api.depends_context("uid")
    def _compute_can_view_private_phone(self):
        access_map = self._get_private_phone_access_map()
        for employee in self:
            employee.can_view_private_phone = access_map.get(employee.id, False)

    @api.depends(
        "work_ratio",
        "assignment_ids.active",
        "assignment_ids.allocation_ratio",
        "assignment_ids.date_start",
        "assignment_ids.date_end",
        "assignment_ids.is_current",
        "assignment_ids.project_id.date_start",
        "assignment_ids.project_id.date_end",
    )
    def _compute_tenenet_assignment_availability(self):
        for rec in self:
            active_assignments = rec.assignment_ids.filtered(lambda assignment: assignment.is_current)
            capacity_ratio = rec.work_ratio or 0.0
            total_ratio = sum(active_assignments.mapped("allocation_ratio"))
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
