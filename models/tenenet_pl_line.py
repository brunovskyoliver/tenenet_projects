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
    amount = fields.Monetary(string="Suma", currency_field="currency_id", default=0.0)
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
