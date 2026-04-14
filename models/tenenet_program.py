from datetime import date

from dateutil.relativedelta import relativedelta
from markupsafe import escape

from odoo import api, fields, models
from odoo.exceptions import ValidationError


PROGRAM_ORG_UNIT_CODE_MAP = {
    "SCPP": "SCPP",
    "SCPAP": "SCPP",
    "NAS_A_VAZ": "KALIA",
}


class TenenetProgram(models.Model):
    _name = "tenenet.program"
    _description = "Program TENENET"
    _order = "name"

    name = fields.Char(string="Názov programu", required=True)
    code = fields.Char(string="Kód programu", required=True)
    organizational_unit_id = fields.Many2one(
        "tenenet.organizational.unit",
        string="Organizačná zložka",
        ondelete="restrict",
        default=lambda self: self.env.ref(
            "tenenet_projects.tenenet_organizational_unit_tenenet_oz",
            raise_if_not_found=False,
        ),
    )
    description = fields.Text(string="Popis")
    active = fields.Boolean(string="Aktívny", default=True)
    is_tenenet_internal = fields.Boolean(
        string="Interný TENENET program",
        default=False,
        help="Technický interný program, ktorý sa nemá zobrazovať v bežnom UI zoznamoch.",
    )
    program_kind = fields.Selection(
        [
            ("service", "Služba"),
            ("management", "Manažment"),
            ("support", "Podpora"),
        ],
        string="Typ programu",
        default="service",
        required=True,
    )
    headcount = fields.Float(
        string="Počet ľudí (FTE)",
        digits=(10, 2),
        compute="_compute_headcount",
        readonly=True,
        help="Aktuálny FTE súčet aktívnych priradení zamestnancov v programe.",
    )
    allocation_pct = fields.Float(
        string="Alokačné %",
        digits=(6, 4),
        compute="_compute_allocation_pct",
    )
    allocation_pct_percentage = fields.Float(
        string="Alokačné percento",
        digits=(6, 4),
        compute="_compute_allocation_pct_percentage",
    )
    reporting_fte = fields.Float(
        string="Reporting FTE",
        digits=(10, 4),
        compute="_compute_reporting_fte",
        readonly=True,
    )
    operating_allocation_pct = fields.Float(
        string="Prevádzková alokácia %",
        digits=(6, 4),
        compute="_compute_operating_allocation_pct",
        readonly=True,
    )
    project_ids = fields.Many2many(
        "tenenet.project",
        "tenenet_project_program_rel",
        "program_id",
        "project_id",
        string="Projekty",
    )
    pl_line_ids = fields.One2many("tenenet.pl.line", "program_id", string="P&L riadky")
    dashboard_active_project_count = fields.Integer(
        string="Aktívne projekty",
        compute="_compute_dashboard_metrics",
    )
    dashboard_current_year_budget_total = fields.Monetary(
        string="Plán rozpočtu za rok",
        currency_field="dashboard_currency_id",
        compute="_compute_dashboard_metrics",
    )
    dashboard_previous_month_wage_total = fields.Monetary(
        string="Mzdy za minulý mesiac",
        currency_field="dashboard_currency_id",
        compute="_compute_dashboard_metrics",
    )
    dashboard_active_fte = fields.Float(
        string="Aktívne FTE",
        digits=(10, 2),
        compute="_compute_dashboard_metrics",
    )
    dashboard_currency_id = fields.Many2one(
        "res.currency",
        string="Mena dashboardu",
        compute="_compute_dashboard_metrics",
    )
    dashboard_html = fields.Html(
        string="Program dashboard",
        compute="_compute_dashboard_metrics",
        sanitize=False,
    )

    _unique_code = models.Constraint("UNIQUE(code)", "Kód programu musí byť jedinečný.")

    @api.model
    def _get_target_organizational_unit(self, program_code):
        unit_code = PROGRAM_ORG_UNIT_CODE_MAP.get(program_code, "TENENET_OZ")
        return self.env["tenenet.organizational.unit"].search([("code", "=", unit_code)], limit=1)

    @api.model
    def _sync_organizational_units(self, force=False):
        for program in self.with_context(active_test=False).search([]):
            if not force and program.organizational_unit_id:
                continue
            target_unit = self._get_target_organizational_unit(program.code)
            if target_unit and program.organizational_unit_id != target_unit:
                program.organizational_unit_id = target_unit

    @api.constrains("active", "is_tenenet_internal", "organizational_unit_id")
    def _check_organizational_unit(self):
        for program in self:
            if program.active and not program.is_tenenet_internal and not program.organizational_unit_id:
                raise ValidationError("Aktívny program musí mať nastavenú organizačnú zložku.")

    def _get_program_assignment_totals(self):
        assignments = self.env["tenenet.project.assignment"].with_context(active_test=False).search([
            ("active", "=", True),
            ("project_id.active", "=", True),
            ("program_id", "in", self.ids),
        ])
        totals = {
            program.id: {
                "fte": 0.0,
                "employees": set(),
            }
            for program in self
        }
        for assignment in assignments:
            ratio = assignment.effective_work_ratio or assignment.allocation_ratio or 0.0
            bucket = totals.setdefault(
                assignment.program_id.id,
                {"fte": 0.0, "employees": set()},
            )
            bucket["fte"] += ratio / 100.0
            if assignment.employee_id:
                bucket["employees"].add(assignment.employee_id.id)
        return totals

    @api.depends(
        "project_ids.assignment_ids.active",
        "project_ids.assignment_ids.program_id",
        "project_ids.assignment_ids.allocation_ratio",
        "project_ids.assignment_ids.effective_work_ratio",
        "project_ids.assignment_ids.employee_id",
        "project_ids.active",
    )
    def _compute_headcount(self):
        totals = self._get_program_assignment_totals()
        for program in self:
            if program.code == "ADMIN_TENENET":
                program.headcount = 0.0
                continue
            program.headcount = totals.get(program.id, {}).get("fte", 0.0)

    @api.depends("headcount")
    def _compute_allocation_pct(self):
        active_programs = self.search([("active", "=", True)]).filtered(
            lambda program: program.code != "ADMIN_TENENET"
        )
        total_headcount = sum(active_programs.mapped("headcount"))
        for program in self:
            if program.code == "ADMIN_TENENET":
                program.allocation_pct = False
                continue
            program.allocation_pct = (program.headcount / total_headcount) if total_headcount else 0.0

    @api.depends("headcount")
    def _compute_allocation_pct_percentage(self):
        active_programs = self.search([("active", "=", True)]).filtered(
            lambda program: program.code != "ADMIN_TENENET"
        )
        total_headcount = sum(active_programs.mapped("headcount"))
        for program in self:
            if program.code == "ADMIN_TENENET":
                program.allocation_pct_percentage = False
                continue
            program.allocation_pct_percentage = ((program.headcount / total_headcount) * 100) if total_headcount else 0.0

    @api.depends(
        "project_ids.assignment_ids.active",
        "project_ids.assignment_ids.program_id",
        "project_ids.assignment_ids.allocation_ratio",
        "project_ids.assignment_ids.effective_work_ratio",
        "project_ids.active",
    )
    def _compute_reporting_fte(self):
        totals = self._get_program_assignment_totals()
        for program in self:
            if program.code == "ADMIN_TENENET":
                program.reporting_fte = 0.0
                continue
            program.reporting_fte = totals.get(program.id, {}).get("fte", 0.0)

    @api.depends("reporting_fte")
    def _compute_operating_allocation_pct(self):
        active_programs = self.search([("active", "=", True)]).filtered(
            lambda program: program.code != "ADMIN_TENENET"
        )
        total_fte = sum(active_programs.mapped("reporting_fte"))
        for program in self:
            if program.code == "ADMIN_TENENET":
                program.operating_allocation_pct = False
                continue
            program.operating_allocation_pct = (
                (program.reporting_fte / total_fte) if total_fte else 0.0
            )

    @api.depends(
        "project_ids.active",
        "project_ids.project_type",
        "project_ids.budget_line_ids.amount",
        "project_ids.budget_line_ids.year",
        "project_ids.assignment_ids.state",
        "project_ids.assignment_ids.program_id",
        "project_ids.assignment_ids.allocation_ratio",
        "project_ids.assignment_ids.effective_work_ratio",
        "project_ids.assignment_ids.employee_id",
        "project_ids.assignment_ids.timesheet_ids.period",
        "project_ids.assignment_ids.timesheet_ids.total_labor_cost",
    )
    def _compute_dashboard_metrics(self):
        today = fields.Date.context_today(self)
        prev_month = fields.Date.to_date(today).replace(day=1) - relativedelta(months=1)
        current_year = fields.Date.to_date(today).year
        company_currency = self.env.company.currency_id
        project_model = self.env["tenenet.project"].with_context(active_test=False)
        assignment_model = self.env["tenenet.project.assignment"].with_context(active_test=False)
        timesheet_model = self.env["tenenet.project.timesheet"].with_context(active_test=False)

        for program in self:
            program.dashboard_currency_id = company_currency
            projects = project_model.search([
                ("program_ids", "in", program.ids),
                ("is_tenenet_internal", "=", False),
            ])
            active_projects = projects.filtered("active")
            assignments = assignment_model.search([
                ("project_id", "in", projects.ids),
                ("program_id", "=", program.id),
                ("state", "=", "active"),
            ])
            previous_month_timesheets = timesheet_model.search([
                ("assignment_id", "in", assignments.ids),
                ("period", "=", prev_month),
            ])
            program.dashboard_active_project_count = len(active_projects)
            program.dashboard_current_year_budget_total = sum(
                projects.mapped("budget_line_ids").filtered(
                    lambda line: line.program_id == program and line.year == current_year
                ).mapped("amount")
            )
            program.dashboard_previous_month_wage_total = sum(previous_month_timesheets.mapped("total_labor_cost"))
            program.dashboard_active_fte = sum(
                (assignment.effective_work_ratio or assignment.allocation_ratio or 0.0) / 100.0
                for assignment in assignments
            )
            program.dashboard_html = program._build_dashboard_html(projects, assignments, previous_month_timesheets, prev_month)

    def _build_dashboard_html(self, projects, assignments, previous_month_timesheets, prev_month):
        self.ensure_one()
        currency = self.env.company.currency_id
        current_year = fields.Date.context_today(self).year
        project_rows = []
        timesheet_amounts = {}
        for timesheet in previous_month_timesheets:
            key = (timesheet.assignment_id.project_id.id, timesheet.assignment_id.employee_id.id)
            timesheet_amounts[key] = timesheet_amounts.get(key, 0.0) + (timesheet.total_labor_cost or 0.0)

        for project in projects.sorted(key=lambda project: (not project.active, project.display_name or "")):
            project_assignments = assignments.filtered(lambda assignment: assignment.project_id == project)
            budget_lines = project.budget_line_ids.filtered(lambda line: line.program_id == self and line.year == current_year)
            budget_summary = ", ".join(
                f"{escape(line.name or line._get_detail_label() or '-')}: "
                f"{currency.symbol or ''} {(line.amount or 0.0):,.2f}".replace(",", " ")
                for line in budget_lines[:4]
            ) or "Bez rozpočtu"
            worker_bits = []
            for assignment in project_assignments.sorted(key=lambda item: item.employee_id.name or ""):
                amount = timesheet_amounts.get((project.id, assignment.employee_id.id), 0.0)
                worker_bits.append(
                    f"<li><strong>{escape(assignment.employee_id.display_name or '-')}</strong>"
                    f"<span>{amount:,.2f} {currency.symbol or ''}</span></li>".replace(",", " ")
                )
            active_fte = sum(
                (assignment.effective_work_ratio or assignment.allocation_ratio or 0.0) / 100.0
                for assignment in project_assignments
            )
            previous_month_wage_total = sum(
                timesheet_amounts.get((project.id, assignment.employee_id.id), 0.0)
                for assignment in project_assignments
            )
            project_type_label = dict(project._fields["project_type"].selection).get(project.project_type, "")
            project_rows.append(
                f"""
                <article class="o_tenenet_program_dashboard_project">
                    <header>
                        <div>
                            <h3><a class="o_tenenet_program_dashboard_project_link" href="/odoo/tenenet.project/{project.id}">{escape(project.display_name or "")}</a></h3>
                            <p>{escape(project_type_label)}</p>
                        </div>
                        <span class="o_tenenet_program_dashboard_badge {'is-active' if project.active else 'is-muted'}">{'Aktívny' if project.active else 'Neaktívny'}</span>
                    </header>
                    <div class="o_tenenet_program_dashboard_project_meta">
                        <div><span>Rozpočet</span><strong>{budget_summary}</strong></div>
                        <div><span>Minulý mesiac</span><strong>{previous_month_wage_total:,.2f} {currency.symbol or ''}</strong></div>
                        <div><span>Aktívni ľudia</span><strong>{len(project_assignments)}</strong></div>
                        <div><span>Aktívne FTE</span><strong>{active_fte:,.2f}</strong></div>
                    </div>
                    <ul class="o_tenenet_program_dashboard_workers">{''.join(worker_bits) or '<li><span>Bez aktívnych pracovníkov</span></li>'}</ul>
                </article>
                """.replace(",", " ")
            )
        return (
            f"<section class='o_tenenet_program_dashboard_list' data-month='{prev_month:%m/%Y}'>"
            f"{''.join(project_rows) or '<div class=\"o_tenenet_program_dashboard_empty\">Program zatiaľ nemá priradené projekty.</div>'}"
            "</section>"
        )
