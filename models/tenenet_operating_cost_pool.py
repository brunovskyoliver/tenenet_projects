from datetime import date

from odoo import api, fields, models


class TenenetOperatingCostPool(models.Model):
    _name = "tenenet.operating.cost.pool"
    _description = "Ročný pool prevádzkových nákladov"
    _order = "year desc"

    name = fields.Char(string="Názov", compute="_compute_name", store=True)
    year = fields.Integer(string="Rok", required=True, default=lambda self: fields.Date.today().year)
    annual_amount = fields.Monetary(string="Ročná suma", currency_field="currency_id", required=True, default=0.0)
    basis_year = fields.Integer(string="Referenčný rok", required=True, default=lambda self: fields.Date.today().year - 1)
    source_note = fields.Text(string="Zdroj / poznámka")
    is_locked = fields.Boolean(string="Uzamknuté", default=False)
    allocation_ids = fields.One2many(
        "tenenet.operating.cost.allocation",
        "pool_id",
        string="Mesačné alokácie",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
        required=True,
    )

    _unique_year = models.Constraint(
        "UNIQUE(year)",
        "Pre rok môže existovať len jeden pool prevádzkových nákladov.",
    )

    @api.depends("year")
    def _compute_name(self):
        for rec in self:
            rec.name = f"Prevádzkové náklady {rec.year}"

    def action_rebuild_allocations(self):
        Allocation = self.env["tenenet.operating.cost.allocation"]
        Program = self.env["tenenet.program"].with_context(active_test=False)
        for rec in self:
            rec.allocation_ids.unlink()
            programs = Program.search([], order="name")
            total_fte = sum(programs.mapped("reporting_fte"))
            for program in programs:
                exact_pct = (program.reporting_fte / total_fte) if total_fte else 0.0
                annual_program_amount = round((rec.annual_amount or 0.0) * exact_pct, 2)
                distributed_amount = 0.0
                for month in range(1, 13):
                    if month < 12:
                        amount = round(annual_program_amount / 12.0, 2)
                        distributed_amount += amount
                    else:
                        amount = round(annual_program_amount - distributed_amount, 2)
                    Allocation.create({
                        "pool_id": rec.id,
                        "program_id": program.id,
                        "period": date(rec.year, month, 1),
                        "allocation_basis_fte": program.reporting_fte,
                        "allocation_pct": exact_pct,
                        "amount": amount,
                        "currency_id": rec.currency_id.id,
                    })
        return True
