import logging
from datetime import date

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

    name = fields.Char(string="Názov projektu", required=True)
    description = fields.Text(string="Popis")
    active = fields.Boolean(string="Aktívny", default=True)
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
        readonly=False,
        help="Kanónický program používaný pre P&L reporting, cashflow a alokácie prevádzkových nákladov.",
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

    @api.depends("program_ids", "program_ids.is_tenenet_internal")
    def _compute_ui_program_ids(self):
        for rec in self:
            rec.ui_program_ids = rec.program_ids.filtered(
                lambda program: not rec._is_hidden_internal_program(program)
            )

    def _inverse_ui_program_ids(self):
        admin_program = self.env["tenenet.program"].with_context(active_test=False).search(
            [("code", "=", self.ADMIN_TENENET_PROGRAM_CODE)],
            limit=1,
        )
        for rec in self:
            visible_programs = rec.ui_program_ids
            target_programs = visible_programs | admin_program
            rec.program_ids = [Command.set(target_programs.ids)]

    @api.depends("program_ids", "program_ids.is_tenenet_internal")
    def _compute_reporting_program_id(self):
        for rec in self:
            visible_programs = rec.program_ids.filtered(
                lambda program: not rec._is_hidden_internal_program(program)
            )
            if rec.reporting_program_id and rec.reporting_program_id in visible_programs:
                continue
            rec.reporting_program_id = visible_programs[:1]

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
        return bool(self.donor_id and self.donor_id.donor_type in {"international", "eu"})

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

    def _get_state_from_amount(self, amount):
        if amount > 0.005:
            return "plus"
        if amount < -0.005:
            return "minus"
        return "neutral"

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
            cashflow_to_date = rec._get_effective_cashflow_total_to_date(today)

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

    def _sync_garant_pm_group(self):
        group = self.env.ref("tenenet_projects.group_tenenet_garant_pm", raise_if_not_found=False)
        group_manager = self.env.ref("tenenet_projects.group_tenenet_manager", raise_if_not_found=False)
        if not group:
            return
        affected = self.mapped("odborny_garant_id") | self.mapped("project_manager_id")
        for employee in affected:
            user = employee.user_id
            if not user:
                continue
            # Managers already have broader access — leave their groups untouched
            if group_manager and group_manager in user.group_ids:
                continue
            still_qualifies = bool(self.env["tenenet.project"].search_count([
                ("active", "=", True),
                "|",
                ("odborny_garant_id", "=", employee.id),
                ("project_manager_id", "=", employee.id),
            ]))
            in_group = group in user.group_ids
            if still_qualifies and not in_group:
                user.write({"group_ids": [(4, group.id)]})
            elif not still_qualifies and in_group:
                user.write({"group_ids": [(3, group.id)]})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_garant_pm_group()
        return records

    def write(self, vals):
        previous_site_ids = {}
        if "site_ids" in vals:
            previous_site_ids = {project.id: set(project.site_ids.ids) for project in self}
        result = super().write(vals)
        if previous_site_ids:
            self._cleanup_assignment_sites_after_project_unlink(previous_site_ids)
        if "date_start" in vals or "date_end" in vals:
            self.mapped("assignment_ids")._sync_precreated_timesheets()
        if "default_max_monthly_wage_hm" in vals:
            self.mapped("assignment_ids.timesheet_ids")._check_wage_cap()
        if "odborny_garant_id" in vals or "project_manager_id" in vals or "active" in vals:
            self._sync_garant_pm_group()
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
        receipts = self.receipt_line_ids.filtered(lambda rec: rec.year == selected_year).sorted(
            key=lambda rec: (rec.date_received or date.min, rec.id),
            reverse=True,
        )
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
        for receipt in receipts:
            active_months = sorted(set(active_months_by_receipt.get(receipt.id, [])))
            rows.append({
                "receipt_id": receipt.id,
                "date_received": fields.Date.to_string(receipt.date_received) if receipt.date_received else False,
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
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.budget.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_project_id": self.id},
        }

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
        admin_program = self.env["tenenet.program"].with_context(active_test=False).search(
            [("code", "=", self.ADMIN_TENENET_PROGRAM_CODE)],
            limit=1,
        )
        if not admin_program:
            admin_program = self._ensure_admin_tenenet_entities().reporting_program_id
        for vals in vals_list:
            if vals.get("is_tenenet_internal"):
                continue
            commands = list(vals.get("program_ids") or [])
            existing_ids = set()
            for command in commands:
                if not isinstance(command, (list, tuple)) or not command:
                    continue
                if command[0] == 6:
                    existing_ids.update(command[2] or [])
                elif command[0] == 4:
                    existing_ids.add(command[1])
            if admin_program.id not in existing_ids:
                commands.append((4, admin_program.id))
            vals["program_ids"] = commands
        return super().create(vals_list)

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
