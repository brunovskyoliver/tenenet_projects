from odoo import api, fields, models


class TenenetProgramSalesEntry(models.Model):
    _name = "tenenet.program.sales.entry"
    _description = "Tržba programu"
    _order = "period desc, program_id, sale_type"

    name = fields.Char(string="Názov", compute="_compute_name", store=True)
    program_id = fields.Many2one("tenenet.program", string="Program", required=True, ondelete="cascade")
    period = fields.Date(string="Obdobie", required=True, help="Prvý deň mesiaca.")
    year = fields.Integer(string="Rok", compute="_compute_year_month", store=True)
    month = fields.Integer(string="Mesiac", compute="_compute_year_month", store=True)
    sale_type = fields.Selection(
        [
            ("cash_register", "Tržby z registračky"),
            ("invoice", "Tržby z faktúr"),
            ("legacy_unclassified", "Tržby - neklasifikované"),
        ],
        string="Typ tržby",
        required=True,
        default="legacy_unclassified",
    )
    amount = fields.Monetary(string="Suma", currency_field="currency_id", required=True, default=0.0)
    site_id = fields.Many2one("tenenet.project.site", string="Prevádzka", ondelete="set null")
    source_ref = fields.Char(string="Zdrojový doklad")
    note = fields.Char(string="Poznámka")
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
        required=True,
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

    @api.depends("program_id", "sale_type", "period")
    def _compute_name(self):
        labels = dict(self._fields["sale_type"].selection)
        for rec in self:
            period_label = rec.period.strftime("%m/%Y") if rec.period else ""
            rec.name = f"{rec.program_id.display_name or ''} / {labels.get(rec.sale_type, '')} / {period_label}".strip(" /")

    @api.model
    def _normalize_period(self, period):
        return fields.Date.to_date(period).replace(day=1)

    @api.model_create_multi
    def create(self, vals_list):
        normalized_vals = []
        for vals in vals_list:
            values = dict(vals)
            if values.get("period"):
                values["period"] = self._normalize_period(values["period"])
            normalized_vals.append(values)
        return super().create(normalized_vals)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("period"):
            vals["period"] = self._normalize_period(vals["period"])
        return super().write(vals)
