from odoo import api, fields, models


class TenenetProjectReceipt(models.Model):
    _name = "tenenet.project.receipt"
    _description = "Príjem projektu"
    _order = "date_received desc"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
    )
    date_received = fields.Date(string="Dátum prijatia", required=True)
    year = fields.Integer(
        string="Rok",
        compute="_compute_year",
        store=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="project_id.currency_id",
        store=True,
    )
    amount = fields.Monetary(string="Prijaté (€)", currency_field="currency_id", default=0.0)
    note = fields.Char(string="Poznámka")

    @api.depends("date_received")
    def _compute_year(self):
        for rec in self:
            rec.year = rec.date_received.year if rec.date_received else 0
