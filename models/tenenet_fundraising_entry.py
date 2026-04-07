from odoo import api, fields, models


class TenenetFundraisingEntry(models.Model):
    _name = "tenenet.fundraising.entry"
    _description = "Príspevok do zbierky"
    _order = "date_received desc, campaign_id"

    name = fields.Char(string="Názov", compute="_compute_name", store=True)
    campaign_id = fields.Many2one(
        "tenenet.fundraising.campaign",
        string="Zbierka",
        required=True,
        ondelete="cascade",
    )
    program_id = fields.Many2one(
        "tenenet.program",
        string="Program",
        related="campaign_id.program_id",
        store=True,
        readonly=True,
    )
    date_received = fields.Date(string="Dátum prijatia", required=True)
    year = fields.Integer(string="Rok", compute="_compute_year_month", store=True)
    month = fields.Integer(string="Mesiac", compute="_compute_year_month", store=True)
    amount = fields.Monetary(string="Suma", currency_field="currency_id", required=True, default=0.0)
    source_ref = fields.Char(string="Zdrojový odkaz")
    note = fields.Char(string="Poznámka")
    currency_id = fields.Many2one(
        "res.currency",
        related="campaign_id.currency_id",
        store=True,
        readonly=True,
    )

    @api.depends("campaign_id", "date_received", "amount")
    def _compute_name(self):
        for rec in self:
            date_label = rec.date_received.strftime("%d.%m.%Y") if rec.date_received else ""
            rec.name = f"{rec.campaign_id.display_name or ''} / {date_label} / {rec.amount or 0.0}"

    @api.depends("date_received")
    def _compute_year_month(self):
        for rec in self:
            if rec.date_received:
                rec.year = rec.date_received.year
                rec.month = rec.date_received.month
            else:
                rec.year = 0
                rec.month = 0
