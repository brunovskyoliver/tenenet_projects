import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import _, Command, api, fields, models
from odoo.exceptions import AccessError, ValidationError

_logger = logging.getLogger(__name__)


class TenenetProject(models.Model):
    _name = "tenenet.project"
    _description = "Projekt TENENET"
    _order = "name"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    ADMIN_TENENET_PROGRAM_CODE = "ADMIN_TENENET"
    ADMIN_TENENET_NAME = "Admin TENENET"
    PROJECT_TYPE_SELECTION = [
        ("narodny", "Národný"),
        ("medzinarodny", "Medzinárodný"),
        ("sluzby", "Služby"),
    ]

    name = fields.Char(string="Názov projektu", required=True)
    description = fields.Text(string="Popis")
    active = fields.Boolean(string="Aktívny", default=True)
    is_recurring_license_project = fields.Boolean(
        string="Licenčný projekt (opakujúci sa)",
        default=False,
    )
    recurring_clone_anchor_date = fields.Date(
        string="Dátum ďalšieho klonovania",
        copy=False,
    )
    recurring_clone_interval_type = fields.Selection(
        [
            ("days", "Denne"),
            ("weeks", "Týždenne"),
            ("months", "Mesačne"),
            ("years", "Ročne"),
        ],
        string="Opakovanie",
        default="years",
        copy=False,
    )
    recurring_last_clone_date = fields.Date(
        string="Naposledy klonované",
        copy=False,
        readonly=True,
    )
    recurring_next_clone_date = fields.Date(
        string="Najbližšie klonovanie",
        compute="_compute_recurring_next_clone_date",
        store=True,
    )
    recurring_root_project_id = fields.Many2one(
        "tenenet.project",
        string="Koreň opakovaného projektu",
        ondelete="set null",
        copy=False,
        readonly=True,
    )
    recurring_source_project_id = fields.Many2one(
        "tenenet.project",
        string="Zdroj posledného klonu",
        ondelete="set null",
        copy=False,
        readonly=True,
    )
    recurring_base_name = fields.Char(
        string="Základ názvu opakovaného projektu",
        copy=False,
    )
    is_tenenet_internal = fields.Boolean(
        string="Interný TENENET projekt",
        default=False,
        help="Interný projekt pre náklady absencií, ktoré nie sú pokryté projektovými pravidlami.",
    )
    contract_number = fields.Char(string="Číslo zmluvy")
    duration = fields.Integer(string="Trvanie (mesiace)", compute="_compute_duration", store=True)
    recipient_name = fields.Char(string="Príjemca", related="recipient_partner_id.name", store=True, readonly=True, translate=False)
    recipient_partner_id = fields.Many2one(
        "res.partner",
        string="Príjemca",
        ondelete="set null",
        default=lambda self: self.env["res.partner"].search([("name", "=", "TENENET o.z.")], limit=1),
    )
    date_contract = fields.Date(string="Dátum podpisania zmluvy")
    date_start = fields.Date(string="Začiatok")
    date_end = fields.Date(string="Koniec")
    partner_id = fields.Many2one("res.partner", string="Partner", ondelete="restrict")
    partners = fields.Char(string="Partneri", related="partner_id.name", store=True, readonly=True)
    portal = fields.Char(string="Portál")

    semaphore = fields.Selection(
        [("green", "Zelená"), ("orange", "oranžová"), ("red", "Červená")],
        string="Semafor",
    )

    program_ids = fields.Many2many(
        "tenenet.program",
        "tenenet_project_program_rel",
        "project_id",
        "program_id",
        string="Programy",
    )
    project_type = fields.Selection(
        PROJECT_TYPE_SELECTION,
        string="Typ",
        required=True,
        default="narodny",
        tracking=True,
    )
    primary_program_id = fields.Many2one(
        "tenenet.program",
        string="Hlavný program",
        compute="_compute_primary_program_id",
        inverse="_inverse_primary_program_id",
        ondelete="restrict",
    )
    ui_program_ids = fields.Many2many(
        "tenenet.program",
        compute="_compute_ui_program_ids",
        inverse="_inverse_ui_program_ids",
        string="Programy",
    )
    reporting_program_id = fields.Many2one(
        "tenenet.program",
        string="Reporting program",
        ondelete="restrict",
        compute="_compute_reporting_program_id",
        store=True,
        readonly=True,
        help="Kanónický program používaný pre P&L reporting, cashflow a alokácie prevádzkových nákladov.",
    )
    organizational_unit_override_id = fields.Many2one(
        "tenenet.organizational.unit",
        string="Organizačná zložka (override)",
        ondelete="restrict",
        help="Voliteľné prepísanie organizačnej zložky načítanej z reporting programu.",
    )
    organizational_unit_id = fields.Many2one(
        "tenenet.organizational.unit",
        string="Organizačná zložka",
        compute="_compute_organizational_unit_id",
        store=True,
        readonly=True,
    )
    site_ids = fields.Many2many(
        "tenenet.project.site",
        "tenenet_project_site_rel",
        "project_id",
        "site_id",
        string="Prevádzky / centrá / terén",
    )
    contact_ids = fields.Many2many(
        "tenenet.project.contact",
        "tenenet_project_contact_rel",
        "project_id",
        "contact_id",
        string="Kontakty projektu",
    )
    donor_id = fields.Many2one("tenenet.donor", string="Donor", ondelete="restrict")
    international = fields.Boolean(
        string="Medzinárodný",
        default=False,
        help="Legacy príznak. Klasifikácia medzinárodného projektu sa v reportoch odvodzuje z typu donora.",
    )

    odborny_garant_id = fields.Many2one("hr.employee", string="Odborný garant")
    project_manager_id = fields.Many2one("hr.employee", string="Projektový manažér")
    allocation_ids = fields.One2many(
        "tenenet.employee.allocation",
        "project_id",
        string="Alokácie (archiv)",
    )
    assignment_ids = fields.One2many(
        "tenenet.project.assignment",
        "project_id",
        string="Priradenia zamestnancov",
    )
    leave_rule_ids = fields.One2many(
        "tenenet.project.leave.rule",
        "project_id",
        string="Pravidlá dovolenky",
    )
    timesheet_ids = fields.One2many(
        "tenenet.project.timesheet",
        "project_id",
        string="Timesheety",
    )
    cashflow_ids = fields.One2many(
        "tenenet.project.cashflow",
        "project_id",
        string="Predikovaný cashflow",
    )
    finance_graph_year = fields.Integer(
        string="Rok grafu",
        default=lambda self: fields.Date.context_today(self).year,
    )
    finance_monthly_comparison_line_ids = fields.One2many(
        "tenenet.project.finance.monthly.line",
        "project_id",
        compute="_compute_finance_monthly_comparison_line_ids",
        string="Mesačné porovnanie cashflow a výdavkov",
        readonly=True,
    )
    finance_monthly_comparison_state = fields.Json(
        compute="_compute_finance_monthly_comparison_state",
        string="Graf porovnania cashflow a výdavkov",
    )
    receipt_line_ids = fields.One2many(
        "tenenet.project.receipt",
        "project_id",
        string="Prijaté podľa rokov",
    )
    budget_line_ids = fields.One2many(
        "tenenet.project.budget.line",
        "project_id",
        string="Rozpočtové položky",
    )
    budget_pausal_line_ids = fields.One2many(
        "tenenet.project.budget.line",
        compute="_compute_budget_type_line_ids",
        string="Paušálne položky",
    )
    budget_labor_line_ids = fields.One2many(
        "tenenet.project.budget.line",
        compute="_compute_budget_type_line_ids",
        string="Mzdové položky",
    )
    budget_other_line_ids = fields.One2many(
        "tenenet.project.budget.line",
        compute="_compute_budget_type_line_ids",
        string="Iné položky",
    )
    milestone_ids = fields.One2many(
        "tenenet.project.milestone",
        "project_id",
        string="Míľniky",
    )
    can_manage_milestones = fields.Boolean(
        string="Môže spravovať míľniky",
        compute="_compute_can_manage_milestones",
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
    )
    budget_total = fields.Monetary(
        string="Prijaté spolu (€)",
        currency_field="currency_id",
        compute="_compute_budget_total",
        store=True,
    )
    budget_pausal_total = fields.Monetary(
        string="Paušálne spolu",
        currency_field="currency_id",
        compute="_compute_budget_type_totals",
        store=True,
    )
    budget_labor_total = fields.Monetary(
        string="Mzdové spolu",
        currency_field="currency_id",
        compute="_compute_budget_type_totals",
        store=True,
    )
    budget_other_total = fields.Monetary(
        string="Iné spolu",
        currency_field="currency_id",
        compute="_compute_budget_type_totals",
        store=True,
    )
    finance_actual_vs_plan_to_date_amount = fields.Monetary(
        string="Predikované financie mínus výdavky do dneška",
        currency_field="currency_id",
        compute="_compute_finance_kpis",
    )
    finance_actual_vs_plan_to_date_state = fields.Selection(
        [("plus", "V pluse"), ("minus", "V mínuse"), ("neutral", "Na nule")],
        string="Stav predikovaných financií do dneška",
        compute="_compute_finance_kpis",
    )
    finance_cashflow_to_date_amount = fields.Monetary(
        string="Stav podľa cashflow plánu",
        currency_field="currency_id",
        compute="_compute_finance_kpis",
    )
    finance_cashflow_to_date_state = fields.Selection(
        [("plus", "V pluse"), ("minus", "V mínuse"), ("neutral", "Na nule")],
        string="Stav podľa cashflow plánu",
        compute="_compute_finance_kpis",
    )
    finance_forecast_total_amount = fields.Monetary(
        string="Zostatok financií projektu",
        currency_field="currency_id",
        compute="_compute_finance_kpis",
    )
    finance_forecast_total_state = fields.Selection(
        [("plus", "V pluse"), ("minus", "V mínuse"), ("neutral", "Na nule")],
        string="Stav zostatku financií",
        compute="_compute_finance_kpis",
    )
    allocation_summary_html = fields.Html(
        string="Aktuálne alokačné % programov",
        compute="_compute_allocation_summary_html",
        sanitize=False,
    )
    kanban_color = fields.Integer(
        string="Farba kanban",
        compute="_compute_kanban_color",
        store=True,
    )
    default_max_monthly_wage_hm = fields.Float(
        string="Max. mesačná mzda HM (predvolená)",
        digits=(10, 4),
        default=0.0,
        help="Predvolený mesačný strop hrubej mzdy pre priradenia na tomto projekte. 0 = bez stropu.",
    )
    default_max_monthly_wage_ccp = fields.Float(
        string="Max. mesačná sadzba CCP (predvolená)",
        digits=(10, 4),
        compute="_compute_default_max_monthly_wage_ccp",
        store=True,
        help="Predvolený mesačný strop CCP = max. mzda HM × 1.362",
    )
    donor_contact = fields.Text(string="Kontakt donor", compute="_compute_donor_contact", store=True)
    partner_contact = fields.Text(string="Kontakt partner", compute="_compute_partner_contact", store=True)
    allowed_expense_type_ids = fields.One2many(
        "tenenet.project.allowed.expense.type",
        "project_id",
        string="Povolené typy výdavkov",
    )
    expense_ids = fields.One2many(
        "tenenet.project.expense",
        "project_id",
        string="Výdavky projektu",
    )
    active_year_from = fields.Integer(
        string="Rok od",
        compute="_compute_active_year_range",
        store=True,
    )
    active_year_to = fields.Integer(
        string="Rok do",
        compute="_compute_active_year_range",
        store=True,
    )
    cashflow_planner_state = fields.Json(
        string="Cashflow planner",
        compute="_compute_cashflow_planner_state",
    )

    @api.depends("date_start", "date_end")
    def _compute_active_year_range(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                rec.active_year_from = min(rec.date_start.year, rec.date_end.year)
                rec.active_year_to = max(rec.date_start.year, rec.date_end.year)
            elif rec.date_start:
                rec.active_year_from = rec.date_start.year
                rec.active_year_to = rec.date_start.year
            elif rec.date_end:
                rec.active_year_from = rec.date_end.year
                rec.active_year_to = rec.date_end.year
            else:
                rec.active_year_from = False
                rec.active_year_to = False

    @api.depends(
        "is_recurring_license_project",
        "recurring_clone_anchor_date",
        "recurring_clone_interval_type",
        "recurring_last_clone_date",
    )
    def _compute_recurring_next_clone_date(self):
        for rec in self:
            if not rec.is_recurring_license_project or not rec.recurring_clone_anchor_date:
                rec.recurring_next_clone_date = False
                continue
            if rec.recurring_last_clone_date:
                rec.recurring_next_clone_date = rec._shift_recurring_date(rec.recurring_last_clone_date)
            else:
                rec.recurring_next_clone_date = rec.recurring_clone_anchor_date

    def _compute_cashflow_planner_state(self):
        current_year = fields.Date.context_today(self).year
        for rec in self:
            rec.cashflow_planner_state = {
                "project_id": rec.id or False,
                "current_year": current_year,
            }

    def _is_hidden_internal_program(self, program):
        return bool(
            program
            and (
                program.is_tenenet_internal
                or program.code == self.ADMIN_TENENET_PROGRAM_CODE
            )
        )

    def _get_visible_programs(self):
        self.ensure_one()
        return self.program_ids.filtered(lambda program: not self._is_hidden_internal_program(program))

    def _get_admin_tenenet_program(self):
        return self.env["tenenet.program"].with_context(active_test=False).search(
            [("code", "=", self.ADMIN_TENENET_PROGRAM_CODE)],
            limit=1,
        )

    def _is_admin_primary_management_project(self):
        self.ensure_one()
        admin_program = self._get_admin_tenenet_program()
        return bool(
            admin_program
            and not self.is_tenenet_internal
            and self.project_type != "medzinarodny"
            and admin_program in self.program_ids
            and not self._get_visible_programs()
        )

    def _get_primary_visible_program(self):
        self.ensure_one()
        visible_programs = self._get_visible_programs()
        if self.primary_program_id and self.primary_program_id in visible_programs:
            return self.primary_program_id
        if self.reporting_program_id and self.reporting_program_id in visible_programs:
            return self.reporting_program_id
        admin_program = self._get_admin_tenenet_program()
        if admin_program and admin_program in self.program_ids and not visible_programs:
            return admin_program
        return visible_programs[:1]

    def _get_effective_reporting_program(self):
        self.ensure_one()
        if self.is_tenenet_internal or self.project_type == "medzinarodny":
            return self._get_admin_tenenet_program()
        return self._get_primary_visible_program()

    @api.depends("program_ids", "program_ids.is_tenenet_internal", "project_type")
    def _compute_ui_program_ids(self):
        for rec in self:
            visible_programs = rec._get_visible_programs()
            if visible_programs:
                rec.ui_program_ids = visible_programs
            elif rec._is_admin_primary_management_project():
                rec.ui_program_ids = rec._get_admin_tenenet_program()
            else:
                rec.ui_program_ids = self.env["tenenet.program"]

    def _inverse_ui_program_ids(self):
        admin_program = self.env["tenenet.program"].with_context(active_test=False).search(
            [("code", "=", self.ADMIN_TENENET_PROGRAM_CODE)],
            limit=1,
        )
        for rec in self:
            visible_programs = rec.ui_program_ids
            if rec.project_type == "medzinarodny":
                target_programs = admin_program
            else:
                target_programs = visible_programs[:1] | admin_program
            rec.with_context(skip_program_type_normalization=True).write({
                "program_ids": [Command.set(target_programs.ids)],
            })

    @api.depends("program_ids", "program_ids.is_tenenet_internal", "project_type")
    def _compute_reporting_program_id(self):
        for rec in self:
            rec.reporting_program_id = rec._get_effective_reporting_program()

    @api.depends("program_ids", "program_ids.is_tenenet_internal", "project_type")
    def _compute_primary_program_id(self):
        for rec in self:
            rec.primary_program_id = False if rec.project_type == "medzinarodny" else rec._get_primary_visible_program()

    @api.depends(
        "organizational_unit_override_id",
        "reporting_program_id",
        "reporting_program_id.organizational_unit_id",
    )
    def _compute_organizational_unit_id(self):
        for rec in self:
            rec.organizational_unit_id = (
                rec.organizational_unit_override_id
                or rec.reporting_program_id.organizational_unit_id
            )

    def _inverse_primary_program_id(self):
        admin_program = self._get_admin_tenenet_program()
        for rec in self:
            if rec.project_type == "medzinarodny":
                rec.with_context(skip_program_type_normalization=True).write({
                    "program_ids": [Command.set(admin_program.ids)],
                })
            else:
                target_programs = (rec.primary_program_id | admin_program) if rec.primary_program_id else admin_program
                rec.with_context(skip_program_type_normalization=True).write({
                    "program_ids": [Command.set(target_programs.ids)],
                })

    def _normalize_program_ids_for_type(self, values, project_type=None):
        admin_program = self.env["tenenet.program"].with_context(active_test=False).search(
            [("code", "=", self.ADMIN_TENENET_PROGRAM_CODE)],
            limit=1,
        )
        current_project_type = self[:1].project_type if self else "narodny"
        project_type = project_type or values.get("project_type") or current_project_type or "narodny"
        primary_program = (
            values.get("primary_program_id")
            and self.env["tenenet.program"].browse(values["primary_program_id"]).exists()
        ) or False
        reporting_program = (
            values.get("reporting_program_id")
            and self.env["tenenet.program"].browse(values["reporting_program_id"]).exists()
        ) or False
        visible_program_ids = set()
        program_commands = list(values.get("program_ids") or [])
        for command in program_commands:
            if not isinstance(command, (list, tuple)) or not command:
                continue
            if command[0] == 6:
                visible_program_ids.update(command[2] or [])
            elif command[0] == 4:
                visible_program_ids.add(command[1])
        if not visible_program_ids and self.ids:
            visible_program_ids.update(self.program_ids.ids)
        selected_programs = self.env["tenenet.program"].browse(list(visible_program_ids)).exists()
        visible_programs = selected_programs.filtered(
            lambda program: not self._is_hidden_internal_program(program)
        )
        if primary_program:
            if primary_program == admin_program:
                visible_programs = self.env["tenenet.program"]
                selected_programs = admin_program
            else:
                visible_programs = primary_program
        elif reporting_program and not self._is_hidden_internal_program(reporting_program):
            visible_programs = reporting_program
        if project_type == "medzinarodny":
            target_programs = admin_program
        elif admin_program and selected_programs == admin_program and not visible_programs:
            target_programs = admin_program
        elif visible_programs:
            target_programs = visible_programs[:1] | admin_program
        else:
            target_programs = self.env["tenenet.program"]
        values["program_ids"] = [Command.set(target_programs.ids)]
        if project_type == "medzinarodny":
            values["primary_program_id"] = False
        elif admin_program and target_programs == admin_program:
            values["primary_program_id"] = admin_program.id
        elif target_programs.filtered(lambda program: not self._is_hidden_internal_program(program)):
            values["primary_program_id"] = target_programs.filtered(
                lambda program: not self._is_hidden_internal_program(program)
            )[:1].id
        return values

    @api.constrains("project_type", "program_ids", "is_tenenet_internal")
    def _check_project_type_program_rules(self):
        admin_program = self.env["tenenet.program"].with_context(active_test=False).search(
            [("code", "=", self.ADMIN_TENENET_PROGRAM_CODE)],
            limit=1,
        )
        for rec in self:
            if rec.is_tenenet_internal:
                continue
            visible_programs = rec._get_visible_programs()
            if admin_program not in rec.program_ids:
                raise ValidationError("Projekt musí mať vždy priradený skrytý program Admin TENENET.")
            if rec.project_type == "medzinarodny":
                if visible_programs:
                    raise ValidationError("Medzinárodný projekt nesmie mať zobrazený vlastný program.")
                continue
            if not visible_programs:
                if admin_program and admin_program in rec.program_ids:
                    continue
                raise ValidationError("Projekt typu národný alebo služby musí mať hlavný program alebo Admin TENENET.")
            if len(visible_programs) != 1:
                raise ValidationError("Projekt typu národný alebo služby musí mať najviac jeden hlavný program.")

    def _get_receipts_for_cashflow_year(self, year):
        self.ensure_one()
        selected_year = int(year or 0)
        if not selected_year:
            return self.env["tenenet.project.receipt"]
        return self.receipt_line_ids.filtered(lambda rec: rec.year == selected_year).sorted(
            key=lambda rec: (rec.date_received or date.min, rec.id),
            reverse=True,
        )

    def _get_cashflow_planner_month_values(self, year, planner_rows=None):
        self.ensure_one()
        month_values = {month: 0.0 for month in range(1, 13)}
        rows = planner_rows
        if rows is None:
            rows = self.get_cashflow_planner_data(year).get("rows", [])
        for row in rows:
            row_months = row.get("months") or {}
            for month in range(1, 13):
                month_values[month] += float(row_months.get(str(month), 0.0) or 0.0)
        return month_values

    def _get_cashflow_breakdown_for_month(self, year, month):
        self.ensure_one()
        total = self._get_cashflow_planner_month_values(year).get(month, 0.0)
        return {
            "total": total,
            "items": [
                {
                    "label": "Celý cashflow",
                    "amount": total,
                },
            ],
        }

    def _get_actual_project_spend_breakdown_for_month(self, year, month):
        self.ensure_one()
        month_start = date(year, month, 1)
        timesheet_cost = sum(
            self.timesheet_ids.filtered(
                lambda rec: rec.period and rec.period == month_start
            ).mapped("total_labor_cost")
        )
        expense_cost = sum(
            self.expense_ids.filtered(
                lambda rec: rec.charged_to == "project"
                and rec.date
                and rec.date.year == year
                and rec.date.month == month
            ).mapped("amount")
        )
        total = timesheet_cost + expense_cost
        return {
            "total": total,
            "items": [
                {"label": "Timesheety", "amount": timesheet_cost},
                {"label": "Projektové výdavky", "amount": expense_cost},
            ],
        }

    CCP_MULTIPLIER = 1.362

    @api.depends("default_max_monthly_wage_hm")
    def _compute_default_max_monthly_wage_ccp(self):
        for rec in self:
            rec.default_max_monthly_wage_ccp = (rec.default_max_monthly_wage_hm or 0.0) * self.CCP_MULTIPLIER

    @api.depends("date_start", "date_end")
    def _compute_duration(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                start_date = min(rec.date_start, rec.date_end)
                end_date = max(rec.date_start, rec.date_end)
                rec.duration = ((end_date.year - start_date.year) * 12) + (
                    end_date.month - start_date.month
                ) + 1
            elif rec.date_start and not rec.date_end:
                current_date = fields.Date.today()
                rec.duration = (current_date.year - rec.date_start.year) * 12 + (
                    current_date.month - rec.date_start.month
                ) + 1
            else:
                rec.duration = False

    @api.depends("donor_id.contact_info")
    def _compute_donor_contact(self):
        for rec in self:
            rec.donor_contact = rec.donor_id.contact_info or False

    @api.depends(
        "partner_id",
        "partner_id.name",
        "partner_id.email",
        "partner_id.phone",
        "partner_id.street",
        "partner_id.street2",
        "partner_id.zip",
        "partner_id.city",
        "partner_id.country_id.name",
        "partner_id.website",
    )
    def _compute_partner_contact(self):
        for rec in self:
            rec.partner_contact = rec._format_partner_contact(rec.partner_id)

    def _is_international_by_donor(self):
        self.ensure_one()
        return self.project_type == "medzinarodny"

    def _is_service_project(self):
        self.ensure_one()
        return self.project_type == "sluzby"

    @api.depends("receipt_line_ids", "receipt_line_ids.amount")
    def _compute_budget_total(self):
        for rec in self:
            rec.budget_total = sum(rec.receipt_line_ids.mapped("amount"))

    @api.depends("budget_line_ids", "budget_line_ids.amount", "budget_line_ids.budget_type")
    def _compute_budget_type_totals(self):
        for rec in self:
            rec.budget_pausal_total = sum(rec.budget_line_ids.filtered(lambda line: line.budget_type == "pausal").mapped("amount"))
            rec.budget_labor_total = sum(rec.budget_line_ids.filtered(lambda line: line.budget_type == "labor").mapped("amount"))
            rec.budget_other_total = sum(rec.budget_line_ids.filtered(lambda line: line.budget_type == "other").mapped("amount"))

    @api.depends("budget_line_ids", "budget_line_ids.budget_type")
    def _compute_budget_type_line_ids(self):
        for rec in self:
            rec.budget_pausal_line_ids = rec.budget_line_ids.filtered(lambda line: line.budget_type == "pausal")
            rec.budget_labor_line_ids = rec.budget_line_ids.filtered(lambda line: line.budget_type == "labor")
            rec.budget_other_line_ids = rec.budget_line_ids.filtered(lambda line: line.budget_type == "other")

    def _get_cashflow_override_map(self, year):
        return self.env["tenenet.cashflow.global.override"].get_year_row_data(year).get(f"income:{self.id}")

    @api.depends("finance_graph_year")
    def _compute_finance_monthly_comparison_line_ids(self):
        line_model = self.env["tenenet.project.finance.monthly.line"]
        for rec in self:
            if not rec.id or not rec.finance_graph_year:
                rec.finance_monthly_comparison_line_ids = line_model.browse()
                continue
            rec.finance_monthly_comparison_line_ids = line_model.search([
                ("project_id", "=", rec.id),
                ("year", "=", rec.finance_graph_year),
            ], order="period asc, series")

    @api.depends("finance_graph_year")
    def _compute_finance_monthly_comparison_state(self):
        for rec in self:
            rec.finance_monthly_comparison_state = {
                "project_id": rec.id or False,
                "current_year": int(rec.finance_graph_year or fields.Date.context_today(self).year),
            }

    def get_finance_monthly_comparison_chart_data(self, year=None):
        self.ensure_one()
        month_labels = [
            "Jan", "Feb", "Mar", "Apr", "Máj", "Jún",
            "Júl", "Aug", "Sep", "Okt", "Nov", "Dec",
        ]
        selected_year = int(year or self.finance_graph_year or fields.Date.context_today(self).year)
        available_years = set(self.receipt_line_ids.mapped("year"))
        available_years |= set(self.cashflow_ids.mapped("receipt_year"))
        available_years |= {
            timesheet.period.year
            for timesheet in self.timesheet_ids
            if timesheet.period
        }
        available_years |= {
            expense.date.year
            for expense in self.expense_ids
            if expense.date
        }
        available_years.add(selected_year)
        planner_data = self.get_cashflow_planner_data(selected_year)
        predicted_values = self._get_cashflow_planner_month_values(
            selected_year,
            planner_rows=planner_data.get("rows", []),
        )
        real_expense_breakdowns = {
            month: self._get_actual_project_spend_breakdown_for_month(selected_year, month)
            for month in range(1, 13)
        }
        predicted_breakdowns = {
            month: self._get_cashflow_breakdown_for_month(selected_year, month)
            for month in range(1, 13)
        }
        return {
            "year": selected_year,
            "available_years": sorted(available_years),
            "months": month_labels,
            "currency_symbol": self.currency_id.symbol or "",
            "currency_position": self.currency_id.position or "after",
            "series": [
                {
                    "key": "predicted_cf",
                    "label": "Predikovaný CF",
                    "values": [predicted_values.get(month, 0.0) for month in range(1, 13)],
                    "tooltips": [
                        {
                            "month": month_labels[month - 1],
                            "total": predicted_breakdowns[month]["total"],
                            "items": predicted_breakdowns[month]["items"],
                        }
                        for month in range(1, 13)
                    ],
                },
                {
                    "key": "real_expense",
                    "label": "Reálne výdavky",
                    "values": [
                        self._get_actual_project_spend_for_month(selected_year, month)
                        for month in range(1, 13)
                    ],
                    "tooltips": [
                        {
                            "month": month_labels[month - 1],
                            "total": real_expense_breakdowns[month]["total"],
                            "items": real_expense_breakdowns[month]["items"],
                        }
                        for month in range(1, 13)
                    ],
                },
            ],
        }

    def _get_effective_cashflow_month_values(self, year):
        self.ensure_one()
        values = {month: 0.0 for month in range(1, 13)}
        for cashflow in self.cashflow_ids.filtered(lambda rec: rec.receipt_year == year):
            values[cashflow.month] += cashflow.amount or 0.0
        override_row = self._get_cashflow_override_map(year)
        if override_row:
            for month in range(1, 13):
                values[month] = (override_row.get("values") or {}).get(month, 0.0)
        return values

    def _get_effective_cashflow_total_to_date(self, today):
        self.ensure_one()
        total = 0.0
        years = set(self.cashflow_ids.mapped("receipt_year"))
        if today.year not in years:
            years.add(today.year)
        for year in years:
            values = self._get_effective_cashflow_month_values(year)
            for month in range(1, 13):
                if date(year, month, 1) <= today.replace(day=1):
                    total += values.get(month, 0.0)
        return total

    def _get_cashflow_planner_total_to_date(self, today):
        self.ensure_one()
        total = 0.0
        years = set(self.receipt_line_ids.mapped("year")) | set(self.cashflow_ids.mapped("receipt_year"))
        if today.year not in years:
            years.add(today.year)
        for year in years:
            values = self._get_cashflow_planner_month_values(year)
            for month in range(1, 13):
                if date(year, month, 1) <= today.replace(day=1):
                    total += values.get(month, 0.0)
        return total

    def _get_state_from_amount(self, amount):
        if amount > 0.005:
            return "plus"
        if amount < -0.005:
            return "minus"
        return "neutral"

    @api.model
    def _sync_finance_monthly_comparison_pairs(self, project_year_pairs):
        pairs_by_project = {}
        for project_id, year in project_year_pairs or set():
            project_id = int(project_id or 0)
            year = int(year or 0)
            if not project_id or not year:
                continue
            pairs_by_project.setdefault(project_id, set()).add(year)

        if not pairs_by_project:
            return

        line_model = self.env["tenenet.project.finance.monthly.line"].sudo()
        for project in self.sudo().browse(sorted(pairs_by_project)):
            if not project.exists():
                continue
            for year in sorted(pairs_by_project[project.id]):
                line_model.sync_project_year(project, year)

    def _sync_finance_monthly_comparison_years(self, years=None):
        self.ensure_one()
        sync_years = {
            int(year or 0)
            for year in (years or [])
            if int(year or 0)
        }
        if not sync_years:
            sync_years.add(int(self.finance_graph_year or fields.Date.context_today(self).year))
        self._sync_finance_monthly_comparison_pairs({
            (self.id, year)
            for year in sync_years
        })

    @api.model
    def _default_recurring_anchor_from_vals(self, vals):
        reference_date = (
            fields.Date.to_date(vals.get("date_end"))
            or fields.Date.to_date(vals.get("date_start"))
            or fields.Date.context_today(self)
        )
        return date(reference_date.year, 12, 31)

    @api.model
    def _normalize_recurring_create_vals(self, vals):
        normalized = dict(vals)
        if normalized.get("is_recurring_license_project"):
            normalized.setdefault(
                "recurring_clone_anchor_date",
                self._default_recurring_anchor_from_vals(normalized),
            )
            normalized.setdefault("recurring_clone_interval_type", "years")
            base_name = (normalized.get("recurring_base_name") or normalized.get("name") or "").strip()
            if base_name:
                normalized.setdefault("recurring_base_name", base_name)
        return normalized

    def _ensure_recurring_metadata(self):
        for rec in self.filtered("is_recurring_license_project"):
            updates = {}
            if not rec.recurring_root_project_id:
                updates["recurring_root_project_id"] = rec.id
            if not rec.recurring_clone_anchor_date:
                updates["recurring_clone_anchor_date"] = rec._default_recurring_anchor_from_vals({
                    "date_start": rec.date_start,
                    "date_end": rec.date_end,
                })
            if not rec.recurring_base_name:
                updates["recurring_base_name"] = rec.name
            if updates:
                super(TenenetProject, rec).write(updates)

    def _get_recurring_delta(self):
        self.ensure_one()
        interval_type = self.recurring_clone_interval_type or "years"
        return relativedelta(**{interval_type: 1})

    def _shift_recurring_date(self, value):
        self.ensure_one()
        value = fields.Date.to_date(value)
        return value + self._get_recurring_delta() if value else False

    def _shift_date_by_recurrence(self, value):
        self.ensure_one()
        value = fields.Date.to_date(value)
        if not value:
            return False
        return value + self._get_recurring_delta()

    def _shift_year_by_recurrence(self, year):
        self.ensure_one()
        if not year:
            return 0
        shifted = date(int(year), 1, 1) + self._get_recurring_delta()
        return shifted.year

    def _get_recurring_root(self):
        self.ensure_one()
        return self.recurring_root_project_id or self

    def _get_recurring_chain_projects(self):
        self.ensure_one()
        root = self._get_recurring_root()
        return self.search([
            ("active", "=", True),
            "|",
            ("id", "=", root.id),
            ("recurring_root_project_id", "=", root.id),
        ], order="create_date desc, id desc")

    def _get_latest_recurring_source(self):
        self.ensure_one()
        chain_projects = self._get_recurring_chain_projects()
        if chain_projects:
            return chain_projects[:1]
        root = self._get_recurring_root()
        if root.active:
            return root
        raise ValidationError("Pre opakované klonovanie nie je dostupný žiadny aktívny zdrojový projekt.")

    def _get_recurring_target_year(self, source_project):
        self.ensure_one()
        reference_date = (
            self._shift_date_by_recurrence(source_project.date_start)
            or self._shift_date_by_recurrence(source_project.date_end)
            or self._shift_date_by_recurrence(self.recurring_next_clone_date)
            or self._shift_date_by_recurrence(fields.Date.context_today(self))
        )
        return reference_date.year

    def _get_recurring_clone_name(self, source_project):
        self.ensure_one()
        root = self._get_recurring_root()
        base_name = root.recurring_base_name or root.name
        return f"{base_name} {self._get_recurring_target_year(source_project)}"

    def _prepare_recurring_project_clone_vals(self, source_project):
        self.ensure_one()
        root = self._get_recurring_root()
        return {
            "name": self._get_recurring_clone_name(source_project),
            "description": source_project.description,
            "active": True,
            "is_recurring_license_project": False,
            "contract_number": source_project.contract_number,
            "recipient_partner_id": source_project.recipient_partner_id.id or False,
            "date_contract": self._shift_date_by_recurrence(source_project.date_contract),
            "date_start": self._shift_date_by_recurrence(source_project.date_start),
            "date_end": self._shift_date_by_recurrence(source_project.date_end),
            "partner_id": source_project.partner_id.id or False,
            "portal": source_project.portal,
            "semaphore": source_project.semaphore,
            "project_type": source_project.project_type,
            "program_ids": [Command.set(source_project.program_ids.ids)],
            "reporting_program_id": source_project.reporting_program_id.id or False,
            "site_ids": [Command.set(source_project.site_ids.ids)],
            "contact_ids": [Command.set(source_project.contact_ids.ids)],
            "donor_id": source_project.donor_id.id or False,
            "international": source_project.international,
            "odborny_garant_id": source_project.odborny_garant_id.id or False,
            "project_manager_id": source_project.project_manager_id.id or False,
            "currency_id": source_project.currency_id.id or False,
            "default_max_monthly_wage_hm": source_project.default_max_monthly_wage_hm,
            "recurring_root_project_id": root.id,
            "recurring_source_project_id": source_project.id,
            "recurring_base_name": root.recurring_base_name or root.name,
        }

    def _clone_project_related_records(self, new_project, source_project):
        self.ensure_one()
        LeaveRule = self.env["tenenet.project.leave.rule"].sudo()
        AllowedExpenseType = self.env["tenenet.project.allowed.expense.type"].sudo()
        BudgetLine = self.env["tenenet.project.budget.line"].sudo()
        Milestone = self.env["tenenet.project.milestone"].sudo()
        Receipt = self.env["tenenet.project.receipt"].sudo()
        Assignment = self.env["tenenet.project.assignment"].sudo()

        for rule in source_project.leave_rule_ids:
            LeaveRule.create({
                "project_id": new_project.id,
                "leave_type_id": rule.leave_type_id.id,
                "included": rule.included,
                "max_leaves_per_year_days": rule.max_leaves_per_year_days,
            })
        for expense_type in source_project.allowed_expense_type_ids:
            AllowedExpenseType.create({
                "project_id": new_project.id,
                "config_id": expense_type.config_id.id or False,
                "name": expense_type.name,
                "description": expense_type.description,
                "max_amount": expense_type.max_amount,
            })
        for budget_line in source_project.budget_line_ids:
            BudgetLine.create({
                "project_id": new_project.id,
                "name": budget_line.name,
                "sequence": budget_line.sequence,
                "year": self._shift_year_by_recurrence(budget_line.year),
                "budget_type": budget_line.budget_type,
                "program_id": budget_line.program_id.id,
                "amount": budget_line.amount,
                "note": budget_line.note,
            })
        for milestone in source_project.milestone_ids:
            Milestone.create({
                "project_id": new_project.id,
                "sequence": milestone.sequence,
                "name": milestone.name,
                "date": self._shift_date_by_recurrence(milestone.date),
                "note": milestone.note,
                "attachment_ids": [Command.set(milestone.attachment_ids.ids)],
            })
        for receipt in source_project.receipt_line_ids:
            cloned_receipt = Receipt.create({
                "project_id": new_project.id,
                "date_received": self._shift_date_by_recurrence(receipt.date_received),
                "amount": receipt.amount,
                "note": receipt.note,
            })
            shifted_cashflow_amounts = {}
            for cashflow in receipt.cashflow_ids:
                shifted_date = self._shift_date_by_recurrence(cashflow.date_start)
                if not shifted_date:
                    continue
                shifted_cashflow_amounts[shifted_date.month] = (
                    shifted_cashflow_amounts.get(shifted_date.month, 0.0) + (cashflow.amount or 0.0)
                )
            if shifted_cashflow_amounts:
                cloned_receipt.set_cashflow_month_amounts(cloned_receipt.year, shifted_cashflow_amounts)
        for assignment in source_project.assignment_ids.filtered(lambda rec: rec.active):
            Assignment.create({
                "employee_id": assignment.employee_id.id,
                "project_id": new_project.id,
                "program_id": assignment.program_id.id or False,
                "site_ids": [Command.set(assignment.site_ids.ids)],
                "date_start": self._shift_date_by_recurrence(assignment.date_start),
                "date_end": self._shift_date_by_recurrence(assignment.date_end),
                "allocation_ratio": assignment.allocation_ratio,
                "settlement_only": assignment.settlement_only,
                "wage_hm": assignment.wage_hm,
                "max_monthly_wage_hm": assignment.max_monthly_wage_hm,
                "active": assignment.active,
            })

    def _run_recurring_clone(self, force=False):
        self.ensure_one()
        root = self._get_recurring_root()
        if not root.is_recurring_license_project:
            raise ValidationError("Opakované klonovanie je dostupné iba pre licenčný opakujúci sa projekt.")
        if not root.recurring_next_clone_date:
            raise ValidationError("Projekt nemá nastavený dátum ďalšieho klonovania.")
        today = fields.Date.context_today(self)
        if not force and root.recurring_next_clone_date > today:
            raise ValidationError("Projekt ešte nie je pripravený na ďalšie klonovanie.")

        source_project = root._get_latest_recurring_source().sudo()
        project_vals = root._prepare_recurring_project_clone_vals(source_project)
        new_project = self.sudo().with_context(
            tracking_disable=True,
            mail_create_nosubscribe=True,
        ).create(project_vals)
        root._clone_project_related_records(new_project, source_project)
        root.sudo().write({
            "recurring_last_clone_date": root.recurring_next_clone_date,
            "recurring_source_project_id": source_project.id,
        })
        return new_project

    def action_test_recurring_clone(self):
        self.ensure_one()
        new_project = self._run_recurring_clone(force=True)
        return {
            "type": "ir.actions.act_window",
            "name": new_project.display_name,
            "res_model": "tenenet.project",
            "view_mode": "form",
            "res_id": new_project.id,
            "target": "current",
        }

    @api.model
    def _cron_run_recurring_project_clones(self):
        today = fields.Date.context_today(self)
        due_projects = self.search([
            ("active", "=", True),
            ("is_tenenet_internal", "=", False),
            ("is_recurring_license_project", "=", True),
            ("recurring_next_clone_date", "!=", False),
            ("recurring_next_clone_date", "<=", today),
        ], order="recurring_next_clone_date asc, id asc")
        for project in due_projects:
            project._run_recurring_clone(force=False)

    def _allocate_annual_amount_by_project_plan(self, year, amount):
        self.ensure_one()
        values = self._get_effective_cashflow_month_values(year)
        total = sum(values.values())
        if total <= 0.0:
            weights = {month: 1.0 / 12.0 for month in range(1, 13)}
        else:
            weights = {month: (values.get(month, 0.0) / total) for month in range(1, 13)}
        currency = self.currency_id or self.env.company.currency_id
        distributed = {}
        running_total = 0.0
        for month in range(1, 13):
            if month < 12:
                month_amount = currency.round((amount or 0.0) * weights[month])
                running_total += month_amount
            else:
                month_amount = currency.round((amount or 0.0) - running_total)
            distributed[month] = month_amount
        return distributed

    def _get_budget_lines_for_year(self, year, budget_type=None, program=None):
        self.ensure_one()
        lines = self.budget_line_ids.filtered(lambda rec: rec.year == year)
        if budget_type:
            lines = lines.filtered(lambda rec: rec.budget_type == budget_type)
        if program:
            lines = lines.filtered(lambda rec: rec.program_id == program)
        return lines

    def _get_actual_project_spend_to_date(self, today):
        self.ensure_one()
        timesheet_cost = sum(
            self.timesheet_ids.filtered(
                lambda rec: rec.period and rec.period <= today.replace(day=1)
            ).mapped("total_labor_cost")
        )
        expense_cost = sum(
            self.expense_ids.filtered(
                lambda rec: rec.charged_to == "project" and rec.date and rec.date <= today
            ).mapped("amount")
        )
        return timesheet_cost + expense_cost

    def _get_actual_project_spend_for_month(self, year, month):
        self.ensure_one()
        month_start = date(year, month, 1)
        timesheet_cost = sum(
            self.timesheet_ids.filtered(
                lambda rec: rec.period and rec.period == month_start
            ).mapped("total_labor_cost")
        )
        expense_cost = sum(
            self.expense_ids.filtered(
                lambda rec: rec.charged_to == "project"
                and rec.date
                and rec.date.year == year
                and rec.date.month == month
            ).mapped("amount")
        )
        return timesheet_cost + expense_cost

    def _get_actual_project_spend_total(self):
        self.ensure_one()
        timesheet_cost = sum(self.timesheet_ids.mapped("total_labor_cost"))
        expense_cost = sum(
            self.expense_ids.filtered(lambda rec: rec.charged_to == "project").mapped("amount")
        )
        return timesheet_cost + expense_cost

    def _get_budget_commitment_to_date(self, today):
        self.ensure_one()
        total = 0.0
        current_month_start = today.replace(day=1)
        for line in self.budget_line_ids:
            if not line.year:
                continue
            if line.year < today.year:
                total += line.amount or 0.0
                continue
            if line.year > today.year:
                continue
            distributed = self._allocate_annual_amount_by_project_plan(line.year, line.amount)
            for month in range(1, 13):
                if date(line.year, month, 1) <= current_month_start:
                    total += distributed.get(month, 0.0)
        return total

    def _get_budget_commitment_total(self):
        self.ensure_one()
        return sum(self.budget_line_ids.mapped("amount"))

    @api.depends(
        "receipt_line_ids.amount",
        "receipt_line_ids.date_received",
        "timesheet_ids.total_labor_cost",
        "timesheet_ids.period",
        "expense_ids.amount",
        "expense_ids.date",
        "expense_ids.charged_to",
        "budget_line_ids.amount",
        "budget_line_ids.year",
        "budget_line_ids.budget_type",
        "cashflow_ids.amount",
        "cashflow_ids.date_start",
        "cashflow_ids.receipt_year",
    )
    def _compute_finance_kpis(self):
        today = fields.Date.context_today(self)
        for rec in self:
            actual_income_to_date = sum(
                rec.receipt_line_ids.filtered(
                    lambda line: line.date_received and line.date_received <= today
                ).mapped("amount")
            )
            total_income = sum(rec.receipt_line_ids.mapped("amount"))
            actual_spend_to_date = rec._get_actual_project_spend_to_date(today)
            cashflow_to_date = rec._get_cashflow_planner_total_to_date(today)
            predicted_balance_to_date = cashflow_to_date - actual_spend_to_date
            remaining_finance_balance = total_income - actual_spend_to_date

            rec.finance_actual_vs_plan_to_date_amount = predicted_balance_to_date
            rec.finance_actual_vs_plan_to_date_state = rec._get_state_from_amount(predicted_balance_to_date)
            rec.finance_cashflow_to_date_amount = predicted_balance_to_date
            rec.finance_cashflow_to_date_state = rec._get_state_from_amount(predicted_balance_to_date)
            rec.finance_forecast_total_amount = remaining_finance_balance
            rec.finance_forecast_total_state = rec._get_state_from_amount(remaining_finance_balance)

    def _get_current_program_allocation_rows(self):
        self.ensure_one()
        assignments = self.assignment_ids.filtered(
            lambda rec: rec.active and rec.program_id and rec.program_id.code != self.ADMIN_TENENET_PROGRAM_CODE
        )
        totals = {}
        total_ratio = 0.0
        for assignment in assignments:
            ratio = assignment.effective_work_ratio or assignment.allocation_ratio or 0.0
            bucket = totals.setdefault(
                assignment.program_id.id,
                {
                    "program": assignment.program_id,
                    "allocation_ratio": 0.0,
                    "allocation_pct": 0.0,
                },
            )
            bucket["allocation_ratio"] += ratio
            total_ratio += ratio
        rows = []
        for row in totals.values():
            row["allocation_pct"] = (row["allocation_ratio"] / total_ratio * 100.0) if total_ratio else 0.0
            rows.append(row)
        rows.sort(key=lambda row: (-row["allocation_pct"], row["program"].display_name))
        return rows

    @api.depends(
        "assignment_ids.active",
        "assignment_ids.program_id",
        "assignment_ids.allocation_ratio",
        "assignment_ids.effective_work_ratio",
    )
    def _compute_allocation_summary_html(self):
        for rec in self:
            rows = rec._get_current_program_allocation_rows()
            if not rows:
                rec.allocation_summary_html = "<p>Pre projekt zatiaľ nie sú dostupné alokačné % programov.</p>"
                continue
            items = "".join(
                f"<li><strong>{row['program'].display_name}</strong>: {row['allocation_pct']:.2f} %"
                f" ({row['allocation_ratio']:.2f} % úväzku)</li>"
                for row in rows
            )
            rec.allocation_summary_html = f"<ul>{items}</ul>"

    @api.depends("semaphore")
    def _compute_kanban_color(self):
        color_map = {"green": 10, "orange": 3, "red": 1}
        for rec in self:
            rec.kanban_color = color_map.get(rec.semaphore, 0)

    @api.depends("odborny_garant_id", "odborny_garant_id.user_id")
    def _compute_can_manage_milestones(self):
        current_user = self.env.user
        is_manager = current_user.has_group("tenenet_projects.group_tenenet_manager")
        employee_ids = set(current_user.employee_ids.ids)
        for rec in self:
            rec.can_manage_milestones = bool(
                is_manager
                or (rec.odborny_garant_id.id and rec.odborny_garant_id.id in employee_ids)
            )

    def _sync_garant_pm_group(self, employees=None):
        group = self.env.ref("tenenet_projects.group_tenenet_garant_pm", raise_if_not_found=False)
        group_manager = self.env.ref("tenenet_projects.group_tenenet_manager", raise_if_not_found=False)
        group_user = self.env.ref("tenenet_projects.group_tenenet_user", raise_if_not_found=False)
        if not group:
            return
        affected = employees or (self.mapped("odborny_garant_id") | self.mapped("project_manager_id"))
        for employee in affected:
            user = employee.user_id
            if not user:
                continue
            in_group = group in user.group_ids
            if group_manager and group_manager in user.group_ids:
                if in_group:
                    user.sudo().write({"group_ids": [(3, group.id)]})
                continue
            still_qualifies = bool(self.env["tenenet.project"].sudo().search_count([
                ("active", "=", True),
                "|",
                ("odborny_garant_id", "=", employee.id),
                ("project_manager_id", "=", employee.id),
            ]))
            if still_qualifies and not in_group:
                commands = [(4, group.id)]
                if group_user and group_user in user.group_ids:
                    commands.append((3, group_user.id))
                user.sudo().write({"group_ids": commands})
            elif still_qualifies and group_user and group_user in user.group_ids:
                user.sudo().write({"group_ids": [(3, group_user.id)]})
            elif not still_qualifies and in_group:
                user.sudo().write({"group_ids": [(3, group.id)]})

    def write(self, vals):
        old_graph_pairs = set()
        vals = dict(vals)
        if (
            not self.env.context.get("skip_program_type_normalization")
            and {"project_type", "program_ids", "primary_program_id"} & set(vals)
        ):
            vals = self._normalize_program_ids_for_type(vals)
        if "project_type" in vals:
            vals["international"] = vals["project_type"] == "medzinarodny"
        if vals.get("is_recurring_license_project") and not vals.get("recurring_clone_anchor_date"):
            vals["recurring_clone_anchor_date"] = self._default_recurring_anchor_from_vals({
                "date_start": vals.get("date_start", self[:1].date_start),
                "date_end": vals.get("date_end", self[:1].date_end),
            })
        if vals.get("is_recurring_license_project") and not vals.get("recurring_base_name"):
            vals["recurring_base_name"] = vals.get("name") or self[:1].recurring_base_name or self[:1].name
        if "finance_graph_year" in vals:
            old_graph_pairs = {
                (record.id, record.finance_graph_year)
                for record in self
                if record.id and record.finance_graph_year
            }
        previous_site_ids = {}
        if "site_ids" in vals:
            previous_site_ids = {project.id: set(project.site_ids.ids) for project in self}
        previous_role_employees = self.env["hr.employee"]
        if {"odborny_garant_id", "project_manager_id", "active"} & set(vals):
            previous_role_employees = self.mapped("odborny_garant_id") | self.mapped("project_manager_id")
        result = super().write(vals)
        if previous_site_ids:
            self._cleanup_assignment_sites_after_project_unlink(previous_site_ids)
        if "date_start" in vals or "date_end" in vals:
            self.mapped("assignment_ids")._sync_precreated_timesheets()
        if "default_max_monthly_wage_hm" in vals:
            self.mapped("assignment_ids.timesheet_ids")._check_wage_cap()
        if "odborny_garant_id" in vals or "project_manager_id" in vals or "active" in vals:
            self._sync_garant_pm_group(previous_role_employees | self.mapped("odborny_garant_id") | self.mapped("project_manager_id"))
        if {"is_recurring_license_project", "recurring_clone_anchor_date", "recurring_base_name"} & set(vals):
            self._ensure_recurring_metadata()
        if "finance_graph_year" in vals:
            self._sync_finance_monthly_comparison_pairs(old_graph_pairs | {
                (record.id, record.finance_graph_year)
                for record in self
                if record.id and record.finance_graph_year
            })
        return result

    def _cleanup_assignment_sites_after_project_unlink(self, previous_site_ids):
        for project in self:
            removed_site_ids = previous_site_ids.get(project.id, set()) - set(project.site_ids.ids)
            if not removed_site_ids:
                continue
            for assignment in project.assignment_ids.filtered(lambda rec: rec.site_ids):
                next_site_ids = [site.id for site in assignment.site_ids if site.id not in removed_site_ids]
                if len(next_site_ids) != len(assignment.site_ids):
                    assignment.write({"site_ids": [Command.set(next_site_ids)]})

    @api.model
    def action_open_garant_projects(self):
        if self.env.user.has_group("tenenet_projects.group_tenenet_manager"):
            domain = [("active", "=", True), ("is_tenenet_internal", "=", False)]
        else:
            domain = [
                ("active", "=", True),
                ("is_tenenet_internal", "=", False),
                "|",
                ("odborny_garant_id.user_id", "=", self.env.uid),
                ("project_manager_id.user_id", "=", self.env.uid),
            ]
        return {
            "name": "Moje projekty (Garant/PM)",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project",
            "view_mode": "kanban,list",
            "domain": domain,
            "views": [
                (self.env.ref("tenenet_projects.view_tenenet_project_garant_kanban").id, "kanban"),
                (False, "list"),
            ],
        }

    def action_open_cashflow_gantt(self):
        self.ensure_one()
        action = self.env.ref("tenenet_projects.action_tenenet_project_cashflow_gantt").read()[0]
        context = dict(self.env.context)
        context.update({
            "default_project_id": self.id,
            "search_default_group_project_label": 1,
            "auto_sync_project_cashflow_labels": True,
        })
        if self.receipt_line_ids:
            # Open to the year of the most recent receipt for convenience
            context["cashflow_initial_year"] = max(self.receipt_line_ids.mapped("year"))
            context["grid_anchor"] = f"{context['cashflow_initial_year']}-01-01"
        action["domain"] = [("project_id", "=", self.id)]
        action["context"] = context
        action["target"] = "current"
        return action

    def get_cashflow_planner_data(self, year=None):
        self.ensure_one()
        selected_year = int(year or fields.Date.context_today(self).year)
        receipts = self._get_receipts_for_cashflow_year(selected_year)
        cashflow_model = self.env["tenenet.project.cashflow"]
        cashflows = cashflow_model.search([
            ("project_id", "=", self.id),
            ("year", "=", selected_year),
            ("receipt_id", "in", receipts.ids),
        ], order="receipt_id, month")

        empty_months = {str(month): 0.0 for month in range(1, 13)}
        months_by_receipt = {receipt.id: dict(empty_months) for receipt in receipts}
        active_months_by_receipt = {receipt.id: [] for receipt in receipts}
        for cashflow in cashflows:
            receipt_id = cashflow.receipt_id.id
            months_by_receipt.setdefault(receipt_id, dict(empty_months))[str(cashflow.month)] = cashflow.amount
            active_months_by_receipt.setdefault(receipt_id, []).append(cashflow.month)

        available_years = sorted({receipt.year for receipt in self.receipt_line_ids if receipt.year})
        if not available_years:
            available_years = [selected_year]

        rows = []
        available_receipts = []
        for receipt in receipts:
            available_receipts.append({
                "id": receipt.id,
                "label": (
                    f"{cashflow_model._format_sk_date(receipt.date_received)} / "
                    f"{cashflow_model._format_sk_amount(receipt.amount)}"
                ),
                "amount": receipt.amount,
                "formatted_amount": cashflow_model._format_sk_amount(receipt.amount),
                "date_received": fields.Date.to_string(receipt.date_received) if receipt.date_received else False,
            })
            active_months = sorted(set(active_months_by_receipt.get(receipt.id, [])))
            rows.append({
                "receipt_id": receipt.id,
                "date_received": fields.Date.to_string(receipt.date_received) if receipt.date_received else False,
                "receipt_month": receipt.date_received.month if receipt.date_received else False,
                "label": (
                    f"{cashflow_model._format_sk_date(receipt.date_received)} / "
                    f"{cashflow_model._format_sk_amount(receipt.amount)}"
                ),
                "formatted_amount": cashflow_model._format_sk_amount(receipt.amount),
                "amount": receipt.amount,
                "note": receipt.note or "",
                "months": months_by_receipt.get(receipt.id, dict(empty_months)),
                "start_month": active_months[0] if active_months else False,
                "end_month": active_months[-1] if active_months else False,
            })

        return {
            "project_id": self.id,
            "project_name": self.display_name,
            "year": selected_year,
            "available_years": available_years,
            "currency_symbol": self.currency_id.symbol or "",
            "currency_position": self.currency_id.position or "after",
            "available_receipts": available_receipts,
            "rows": rows,
        }


    def action_open_receipt_wizard(self):
        self.ensure_one()
        return {
            "name": "Pridať príjem projektu",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.receipt.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_open_assignment_wizard(self):
        self.ensure_one()
        return {
            "name": "Pridať priradenie zamestnanca",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.assignment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_open_budget_wizard(self):
        self.ensure_one()
        return {
            "name": "Pridať rozpočtovú položku",
            "type": "ir.actions.client",
            "tag": "tenenet_budget_add_action",
            "target": "new",
            "params": {"project_id": self.id},
        }

    def get_budget_add_action_data(self):
        self.ensure_one()
        year = fields.Date.context_today(self).year
        budget_line_model = self.env["tenenet.project.budget.line"]
        received = sum(self.receipt_line_ids.filtered(lambda line: line.year == year).mapped("amount"))
        budgeted = sum(self.budget_line_ids.filtered(lambda line: line.year == year).mapped("amount"))
        available = received - budgeted
        return {
            "project_id": self.id,
            "project_name": self.display_name,
            "project_type": self.project_type,
            "project_type_label": dict(self._fields["project_type"].selection).get(self.project_type, ""),
            "year": year,
            "currency_symbol": self.currency_id.symbol or "",
            "currency_position": self.currency_id.position or "after",
            "received_amount": received,
            "budgeted_amount": budgeted,
            "available_amount": available,
            "default_budget_type": "labor",
            "budget_type_options": [
                {"value": value, "label": label}
                for value, label in budget_line_model._fields["budget_type"].selection
            ],
            "expense_type_options": [
                {"id": record.id, "label": record.display_name}
                for record in self.env["tenenet.expense.type.config"].search([("active", "=", True)], order="sequence, name")
            ],
            "service_income_type_options": [
                {"value": value, "label": label}
                for value, label in budget_line_model._fields["service_income_type"].selection
            ],
        }

    def action_create_budget_line_from_quick_add(
        self,
        budget_type,
        amount,
        allocation_percentage=0.0,
        note=None,
        expense_type_config_id=False,
        service_income_type=False,
        can_cover_payroll=False,
    ):
        self.ensure_one()
        year = fields.Date.context_today(self).year
        received = sum(self.receipt_line_ids.filtered(lambda line: line.year == year).mapped("amount"))
        budgeted = sum(self.budget_line_ids.filtered(lambda line: line.year == year).mapped("amount"))
        available = received - budgeted
        amount = float(amount or 0.0)
        allocation_percentage = float(allocation_percentage or 0.0)
        if allocation_percentage < 0.0 or allocation_percentage > 100.0:
            raise ValidationError(_("Percento alokácie musí byť medzi 0 a 100."))
        if amount <= 0.0:
            raise ValidationError(_("Rozpočtová položka musí mať kladnú sumu."))
        if amount > available:
            raise ValidationError(_("Rozpočtová položka prekračuje dostupné prijaté financie za zvolený rok."))

        admin_program = self.env["tenenet.program"].search([("code", "=", self.ADMIN_TENENET_PROGRAM_CODE)], limit=1)
        if budget_type == "pausal":
            program = admin_program
        else:
            program = self.reporting_program_id or self.program_ids.filtered(lambda rec: rec != admin_program)[:1]
        if not program:
            raise ValidationError(_("Pre tento projekt nie je dostupný vhodný program rozpočtu."))

        budget_line_model = self.env["tenenet.project.budget.line"]
        type_label = dict(budget_line_model._fields["budget_type"].selection).get(budget_type, "Rozpočet")
        if service_income_type and not self._is_service_project():
            raise ValidationError(_("Servisné príjmy možno plánovať iba na projekte typu Služby."))
        if budget_type == "other" and not service_income_type and not expense_type_config_id:
            raise ValidationError(_("Pri položke Iné treba vybrať kategóriu výdavku."))
        if can_cover_payroll and not service_income_type:
            raise ValidationError(_("Prepínač mzdového krytia je dostupný iba pre servisné príjmy."))
        detail_name = type_label
        if expense_type_config_id:
            detail_name = self.env["tenenet.expense.type.config"].browse(expense_type_config_id).display_name or detail_name
        elif service_income_type:
            detail_name = dict(budget_line_model._fields["service_income_type"].selection).get(service_income_type, detail_name)
        budget_line = self.env["tenenet.project.budget.line"].create({
            "project_id": self.id,
            "year": year,
            "budget_type": budget_type,
            "program_id": program.id,
            "name": _("%s %s") % (detail_name, year),
            "amount": amount,
            "note": note or False,
            "expense_type_config_id": expense_type_config_id or False,
            "service_income_type": service_income_type or False,
            "can_cover_payroll": bool(can_cover_payroll),
        })
        return budget_line.action_open_planner()

    def action_open_site_wizard(self):
        self.ensure_one()
        return {
            "name": "Pridať prevádzky, centrá alebo terén",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.site.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_open_contact_wizard(self):
        self.ensure_one()
        return {
            "name": "Pridať kontakty projektu",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.contact.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_open_allowed_expense_type_wizard(self):
        self.ensure_one()
        return {
            "name": "Pridať povolený typ výdavku",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.allowed.expense.type.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_open_milestone_wizard(self):
        self.ensure_one()
        self._check_milestone_manage_access()
        return {
            "name": "Pridať míľnik",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.milestone.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }

    def action_open_assignments_kanban(self):
        self.ensure_one()
        return {
            "name": self.name,
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.assignment",
            "view_mode": "kanban,list",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id, "search_default_active": 1},
        }

    def action_open_timesheet_month_matrix(self):
        self.ensure_one()
        self.assignment_ids._sync_precreated_timesheets()
        action = self.env.ref("tenenet_projects.action_tenenet_project_timesheet_matrix").read()[0]
        action["domain"] = [("project_id", "=", self.id)]
        action["context"] = {
            "search_default_group_employee": 1,
            "search_default_group_year": 1,
        }
        return action

    @api.model
    def _ensure_admin_tenenet_entities(self):
        program_model = self.env["tenenet.program"].with_context(active_test=False)
        project_model = self.with_context(active_test=False)

        program = program_model.search([("code", "=", self.ADMIN_TENENET_PROGRAM_CODE)], limit=1)
        if not program:
            program = program_model.create({
                "name": self.ADMIN_TENENET_NAME,
                "code": self.ADMIN_TENENET_PROGRAM_CODE,
                "program_kind": "support",
                "is_tenenet_internal": True,
            })
        elif not program.is_tenenet_internal:
            program.write({"is_tenenet_internal": True, "active": True})

        project = project_model.search([("is_tenenet_internal", "=", True)], limit=1)
        values = {
            "name": self.ADMIN_TENENET_NAME,
            "active": True,
            "is_tenenet_internal": True,
            "project_type": "medzinarodny",
            "reporting_program_id": program.id,
            "program_ids": [(6, 0, [program.id])],
        }
        if project:
            project.write(values)
        else:
            project = project_model.create(values)
        return project

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._normalize_recurring_create_vals(vals) for vals in vals_list]
        admin_program = self.env["tenenet.program"].with_context(active_test=False).search(
            [("code", "=", self.ADMIN_TENENET_PROGRAM_CODE)],
            limit=1,
        )
        if not admin_program:
            admin_program = self._ensure_admin_tenenet_entities().reporting_program_id
        for vals in vals_list:
            if vals.get("is_tenenet_internal"):
                vals.setdefault("project_type", "medzinarodny")
                vals["international"] = True
                vals["program_ids"] = [Command.set(admin_program.ids)]
                continue
            vals.setdefault("project_type", "narodny")
            vals["international"] = vals["project_type"] == "medzinarodny"
            self._normalize_program_ids_for_type(vals, project_type=vals.get("project_type"))
        records = super().create(vals_list)
        records._ensure_recurring_metadata()
        records._sync_garant_pm_group()
        records._sync_finance_monthly_comparison_pairs({
            (record.id, record.finance_graph_year or fields.Date.context_today(self).year)
            for record in records
            if record.id
        })
        return records

    @api.model
    def _format_partner_contact(self, partner):
        if not partner:
            return False

        lines = []
        if partner.name:
            lines.append(partner.name)
        if partner.email:
            lines.append(partner.email)

        phones = [value for value in [partner.phone] if value]
        if phones:
            lines.append(" / ".join(dict.fromkeys(phones)))

        address_parts = [value for value in [partner.street, partner.street2] if value]
        city_line = " ".join(value for value in [partner.zip, partner.city] if value)
        if city_line:
            address_parts.append(city_line)
        if partner.country_id:
            address_parts.append(partner.country_id.name)
        if address_parts:
            lines.append(", ".join(address_parts))

        if partner.website:
            lines.append(partner.website)

        return "\n".join(lines) if lines else False

    def _check_milestone_manage_access(self):
        if self.env.is_superuser():
            return
        current_user = self.env.user
        is_manager = current_user.has_group("tenenet_projects.group_tenenet_manager")
        employee_ids = set(current_user.employee_ids.ids)
        for rec in self:
            is_garant = rec.odborny_garant_id.id in employee_ids
            if not (is_manager or is_garant):
                raise AccessError(
                    _("Míľniky môže upravovať iba TENENET manažér alebo odborný garant projektu.")
                )

    @api.constrains("is_tenenet_internal", "active")
    def _check_single_active_internal_project(self):
        for rec in self:
            if not rec.is_tenenet_internal or not rec.active:
                continue
            duplicate_count = self.search_count([
                ("id", "!=", rec.id),
                ("is_tenenet_internal", "=", True),
                ("active", "=", True),
            ])
            if duplicate_count:
                raise ValidationError(
                    "Môže existovať iba jeden aktívny interný TENENET projekt."
                )

    @api.model
    def _get_or_create_internal_project(self):
        _logger.warning(
            "DEPRECATED: _get_or_create_internal_project is deprecated. "
            "Use tenenet.internal.expense instead of the internal project mechanism."
        )
        return self._ensure_admin_tenenet_entities()
