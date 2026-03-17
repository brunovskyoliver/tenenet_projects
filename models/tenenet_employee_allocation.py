from odoo import api, fields, models


class TenenetEmployeeAllocation(models.Model):
    _name = "tenenet.employee.allocation"
    _description = "Alokácia zamestnanca na projekt"
    _order = "period desc, employee_id, project_id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
    )
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
    )
    period = fields.Date(string="Obdobie", required=True)

    hours_pp = fields.Float(string="Hodiny PP", digits=(10, 2))
    hours_np = fields.Float(string="Hodiny NP", digits=(10, 2))
    hours_travel = fields.Float(string="Hodiny cestovanie", digits=(10, 2))
    hours_training = fields.Float(string="Hodiny školenia", digits=(10, 2))
    hours_ambulance = fields.Float(string="Hodiny ambulancia", digits=(10, 2))
    hours_international = fields.Float(string="Hodiny medzinárodné", digits=(10, 2))
    hours_vacation = fields.Float(string="Hodiny dovolenka", digits=(10, 2))
    hours_sick = fields.Float(string="Hodiny PN", digits=(10, 2))
    hours_doctor = fields.Float(string="Hodiny lekár", digits=(10, 2))
    hours_holidays = fields.Float(string="Hodiny sviatky", digits=(10, 2))

    hours_total = fields.Float(
        string="Hodiny spolu",
        digits=(10, 2),
        compute="_compute_hours_total",
        store=True,
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
    )
    gross_salary = fields.Monetary(string="Hrubá mzda", currency_field="currency_id")
    deductions = fields.Monetary(string="Odvody", currency_field="currency_id")
    total_labor_cost = fields.Monetary(
        string="Celková cena práce",
        currency_field="currency_id",
        compute="_compute_total_labor_cost",
        store=True,
    )

    _unique_employee_project_period = models.Constraint(
        "UNIQUE(employee_id, project_id, period)",
        "Pre zamestnanca, projekt a obdobie môže existovať len jedna alokácia.",
    )

    @api.depends(
        "hours_pp",
        "hours_np",
        "hours_travel",
        "hours_training",
        "hours_ambulance",
        "hours_international",
    )
    def _compute_hours_total(self):
        for rec in self:
            rec.hours_total = (
                (rec.hours_pp or 0.0)
                + (rec.hours_np or 0.0)
                + (rec.hours_travel or 0.0)
                + (rec.hours_training or 0.0)
                + (rec.hours_ambulance or 0.0)
                + (rec.hours_international or 0.0)
            )

    @api.depends("gross_salary", "deductions")
    def _compute_total_labor_cost(self):
        for rec in self:
            rec.total_labor_cost = (rec.gross_salary or 0.0) + (rec.deductions or 0.0)
