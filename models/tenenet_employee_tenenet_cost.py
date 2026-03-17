from odoo import api, fields, models


class TenenetEmployeeTenenetCost(models.Model):
    _name = "tenenet.employee.tenenet.cost"
    _description = "Náklady zamestnanca – Tenenet (reziduum)"
    _order = "period desc, employee_id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
    )
    period = fields.Date(
        string="Obdobie",
        required=True,
        help="Prvý deň mesiaca",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
    )
    gross_salary_employee = fields.Monetary(
        string="Celková hrubá mzda zamestnanca",
        currency_field="currency_id",
        help="Celková hrubá mzda zamestnanca za daný mesiac (z mzdovej agendy)",
    )
    total_labor_cost_employee = fields.Monetary(
        string="Celková cena práce zamestnanca",
        currency_field="currency_id",
        help="Celková cena práce zamestnanca za daný mesiac (z mzdovej agendy)",
    )
    project_billed_gross = fields.Monetary(
        string="Fakturovaná hrubá mzda projektom",
        currency_field="currency_id",
        compute="_compute_residual",
        store=True,
    )
    project_billed_ccp = fields.Monetary(
        string="Fakturovaná CCP projektom",
        currency_field="currency_id",
        compute="_compute_residual",
        store=True,
    )
    tenenet_residual_hm = fields.Monetary(
        string="Reziduum Tenenet – hrubá mzda",
        currency_field="currency_id",
        compute="_compute_residual",
        store=True,
    )
    tenenet_residual_ccp = fields.Monetary(
        string="Reziduum Tenenet – CCP",
        currency_field="currency_id",
        compute="_compute_residual",
        store=True,
    )

    _unique_employee_period = models.Constraint(
        "UNIQUE(employee_id, period)",
        "Pre zamestnanca môže existovať len jeden Tenenet nákladový záznam za obdobie.",
    )

    @api.depends(
        "employee_id",
        "period",
        "gross_salary_employee",
        "total_labor_cost_employee",
        "employee_id.assignment_ids.timesheet_ids.gross_salary",
        "employee_id.assignment_ids.timesheet_ids.total_labor_cost",
        "employee_id.assignment_ids.timesheet_ids.period",
    )
    def _compute_residual(self):
        Timesheet = self.env["tenenet.project.timesheet"]
        for rec in self:
            if not rec.employee_id or not rec.period:
                rec.project_billed_gross = 0.0
                rec.project_billed_ccp = 0.0
                rec.tenenet_residual_hm = 0.0
                rec.tenenet_residual_ccp = 0.0
                continue

            timesheets = Timesheet.search([
                ("employee_id", "=", rec.employee_id.id),
                ("period", "=", rec.period),
            ])
            billed_gross = sum(timesheets.mapped("gross_salary"))
            billed_ccp = sum(timesheets.mapped("total_labor_cost"))

            rec.project_billed_gross = billed_gross
            rec.project_billed_ccp = billed_ccp
            rec.tenenet_residual_hm = (rec.gross_salary_employee or 0.0) - billed_gross
            rec.tenenet_residual_ccp = (rec.total_labor_cost_employee or 0.0) - billed_ccp

    @api.model
    def _sync_for_employee_period(self, employee_id, period):
        """Create or ensure residual record exists for an employee+period after timesheet changes."""
        existing = self.search([
            ("employee_id", "=", employee_id),
            ("period", "=", period),
        ], limit=1)
        if not existing:
            self.create({
                "employee_id": employee_id,
                "period": period,
            })
        else:
            existing._compute_residual()
