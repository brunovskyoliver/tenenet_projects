from odoo import api, fields, models


class TenenetFundraisingCampaign(models.Model):
    _name = "tenenet.fundraising.campaign"
    _description = "Fundraisingová zbierka"
    _order = "date_start desc, name"

    name = fields.Char(string="Názov", required=True)
    active = fields.Boolean(string="Aktívna", default=True)
    program_id = fields.Many2one("tenenet.program", string="Program", required=True, ondelete="restrict")
    target_amount = fields.Monetary(string="Cieľová suma", currency_field="currency_id", default=0.0)
    date_start = fields.Date(string="Začiatok")
    date_end = fields.Date(string="Koniec")
    note = fields.Text(string="Poznámka")
    entry_ids = fields.One2many("tenenet.fundraising.entry", "campaign_id", string="Príspevky")
    raised_amount = fields.Monetary(
        string="Vyzbierané",
        currency_field="currency_id",
        compute="_compute_raised_amount",
        store=True,
    )
    success_ratio = fields.Float(
        string="Úspešnosť",
        digits=(6, 4),
        compute="_compute_raised_amount",
        store=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
        required=True,
    )

    @api.depends("entry_ids.amount", "target_amount")
    def _compute_raised_amount(self):
        for rec in self:
            rec.raised_amount = sum(rec.entry_ids.mapped("amount"))
            rec.success_ratio = (
                rec.raised_amount / rec.target_amount if rec.target_amount else 0.0
            )
