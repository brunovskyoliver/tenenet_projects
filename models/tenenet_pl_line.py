from odoo import api, fields, models


class TenenetPLLine(models.Model):
    _name = "tenenet.pl.line"
    _description = "P&L riadok podľa programu"
    _order = "period desc, program_id, employee_id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
    )
    program_id = fields.Many2one(
        "tenenet.program",
        string="Program",
        required=True,
        ondelete="cascade",
    )
    period = fields.Date(string="Obdobie", required=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
    )
    amount = fields.Monetary(
        string="Suma",
        currency_field="currency_id",
        compute="_compute_amount",
        store=True,
        help="Vypočítané z timesheet záznamov: súčet celkovej ceny práce zamestnanca na projektoch programu za dané obdobie.",
    )
    annual_total = fields.Monetary(
        string="Ročný súčet",
        currency_field="currency_id",
        compute="_compute_annual_total",
        store=True,
    )

    _unique_employee_program_period = models.Constraint(
        "UNIQUE(employee_id, program_id, period)",
        "Pre zamestnanca, program a obdobie môže existovať len jeden P&L riadok.",
    )

    @api.model
    def _sync_for_year(self, selected_year):
        year_start = fields.Date.to_date(f"{selected_year}-01-01")
        year_end = fields.Date.to_date(f"{selected_year}-12-31")
        timesheets = self.env["tenenet.project.timesheet"].with_context(active_test=False).search([
            ("project_id.program_ids", "!=", False),
            ("period", ">=", year_start),
            ("period", "<=", year_end),
        ])

        wanted_keys = {}
        for timesheet in timesheets:
            employee = timesheet.employee_id
            period = timesheet.period
            if not employee or not period:
                continue
            for program in timesheet.project_id.program_ids:
                if not program:
                    continue
                key = (employee.id, program.id, period)
                wanted_keys[key] = {
                    "employee_id": employee.id,
                    "program_id": program.id,
                    "period": period,
                }

        existing_lines = self.search([
            ("period", ">=", year_start),
            ("period", "<=", year_end),
        ])
        existing_by_key = {
            (line.employee_id.id, line.program_id.id, line.period): line
            for line in existing_lines
            if line.employee_id and line.program_id and line.period
        }

        lines_to_delete = existing_lines.filtered(
            lambda line: (line.employee_id.id, line.program_id.id, line.period) not in wanted_keys
        )
        if lines_to_delete:
            lines_to_delete.unlink()

        missing_vals = [
            vals for key, vals in wanted_keys.items()
            if key not in existing_by_key
        ]
        if missing_vals:
            self.create(missing_vals)

        synced_lines = self.search([
            ("period", ">=", year_start),
            ("period", "<=", year_end),
        ])
        if synced_lines:
            synced_lines._compute_amount()
            synced_lines._compute_annual_total()
        return synced_lines

    @api.depends(
        "employee_id",
        "program_id",
        "period",
        "employee_id.assignment_ids.project_id.program_ids",
        "employee_id.assignment_ids.timesheet_ids.period",
        "employee_id.assignment_ids.timesheet_ids.total_labor_cost",
    )
    def _compute_amount(self):
        Timesheet = self.env["tenenet.project.timesheet"]
        for rec in self:
            if not rec.employee_id or not rec.program_id or not rec.period:
                rec.amount = 0.0
                continue
            lines = Timesheet.search([
                ("employee_id", "=", rec.employee_id.id),
                ("project_id.program_ids", "in", [rec.program_id.id]),
                ("period", "=", rec.period),
            ])
            rec.amount = sum(lines.mapped("total_labor_cost"))

    @api.depends(
        "employee_id",
        "program_id",
        "period",
        "amount",
        "employee_id.pl_line_ids.amount",
        "employee_id.pl_line_ids.period",
        "employee_id.pl_line_ids.program_id",
    )
    def _compute_annual_total(self):
        for rec in self:
            if not rec.employee_id or not rec.program_id or not rec.period:
                rec.annual_total = 0.0
                continue

            same_year_lines = rec.employee_id.pl_line_ids.filtered(
                lambda line: line.program_id == rec.program_id
                and line.period
                and line.period.year == rec.period.year
            )
            rec.annual_total = sum(same_year_lines.mapped("amount"))
