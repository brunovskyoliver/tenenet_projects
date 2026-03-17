from odoo import fields, models


class TenenetProjectReceipt(models.Model):
    _name = "tenenet.project.receipt"
    _description = "Ročný príjem projektu"
    _order = "year"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
    )
    year = fields.Integer(string="Rok", required=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        related="project_id.currency_id",
        store=True,
    )
    amount = fields.Monetary(string="Prijaté", currency_field="currency_id", default=0.0)

    _unique_project_year = models.Constraint(
        "UNIQUE(project_id, year)",
        "Pre každý projekt môže existovať len jeden riadok prijatých prostriedkov pre daný rok.",
    )
