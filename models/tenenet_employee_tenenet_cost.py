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
    monthly_gross_salary_target = fields.Monetary(
        string="Mesačná hrubá mzda - cieľ",
        currency_field="currency_id",
        related="employee_id.monthly_gross_salary_target",
        readonly=True,
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
        "employee_id.monthly_gross_salary_target",
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

    def _sync_internal_residual_expense(self):
        InternalExpense = self.env["tenenet.internal.expense"].sudo()
        internal_project = self.env["tenenet.project"].sudo()._ensure_admin_tenenet_entities()
        for rec in self:
            existing = InternalExpense.search([("tenenet_cost_id", "=", rec.id)], limit=1)
            target_hm = rec.employee_id.monthly_gross_salary_target or 0.0
            gap_hm = max(0.0, target_hm - (rec.project_billed_gross or 0.0))
            if gap_hm <= 0.001:
                if existing:
                    existing.unlink()
                continue

            vals = {
                "employee_id": rec.employee_id.id,
                "period": rec.period,
                "category": "residual_wage",
                "source_project_id": internal_project.id,
                "tenenet_cost_id": rec.id,
                "cost_hm": gap_hm,
                "note": "Dorovnanie mesačnej hrubej mzdy do cieľovej hodnoty.",
            }
            if existing:
                existing.write(vals)
            else:
                InternalExpense.create(vals)

    @api.model
    def _sync_for_employee_period(self, employee_id, period):
        """Create or ensure residual record exists for an employee+period after timesheet changes."""
        existing = self.search([
            ("employee_id", "=", employee_id),
            ("period", "=", period),
        ], limit=1)
        if not existing:
            existing = self.create({
                "employee_id": employee_id,
                "period": period,
            })
        else:
            existing._compute_residual()
        existing._sync_internal_residual_expense()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_internal_residual_expense()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._sync_internal_residual_expense()
        return result
