from odoo import api, fields, models


class TenenetOperatingCostAllocation(models.Model):
    _name = "tenenet.operating.cost.allocation"
    _description = "Mesačná alokácia prevádzkových nákladov"
    _order = "period desc, program_id"

    pool_id = fields.Many2one(
        "tenenet.operating.cost.pool",
        string="Pool",
        required=True,
        ondelete="cascade",
    )
    program_id = fields.Many2one("tenenet.program", string="Program", required=True, ondelete="cascade")
    period = fields.Date(string="Obdobie", required=True)
    year = fields.Integer(string="Rok", compute="_compute_year_month", store=True)
    month = fields.Integer(string="Mesiac", compute="_compute_year_month", store=True)
    allocation_basis_fte = fields.Float(string="Reporting FTE", digits=(10, 4), required=True, default=0.0)
    allocation_pct = fields.Float(string="Alokačné %", digits=(6, 4), required=True, default=0.0)
    amount = fields.Monetary(string="Suma", currency_field="currency_id", required=True, default=0.0)
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
        required=True,
    )

    _unique_pool_program_period = models.Constraint(
        "UNIQUE(pool_id, program_id, period)",
        "Pre program a obdobie môže existovať len jedna prevádzková alokácia v rámci poolu.",
    )

    @api.depends("period")
    def _compute_year_month(self):
        for rec in self:
            if rec.period:
                rec.year = rec.period.year
                rec.month = rec.period.month
            else:
                rec.year = 0
                rec.month = 0
