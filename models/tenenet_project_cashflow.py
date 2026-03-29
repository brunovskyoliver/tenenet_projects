from odoo import api, fields, models


class TenenetProjectCashflow(models.Model):
    _name = "tenenet.project.cashflow"
    _description = "Predikovaný cashflow projektu"
    _order = "date_start asc"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
    )
    receipt_id = fields.Many2one(
        "tenenet.project.receipt",
        string="Príjem",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(
        string="Názov",
        compute="_compute_name",
        store=True,
    )
    date_start = fields.Date(string="Začiatok", required=True)
    date_stop = fields.Date(string="Koniec", required=True)
    year = fields.Integer(string="Rok", compute="_compute_year_month", store=True)
    month = fields.Integer(string="Mesiac", compute="_compute_year_month", store=True)
    amount = fields.Monetary(string="Suma (€)", currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency",
        related="project_id.currency_id",
        store=True,
    )
    row_label = fields.Char(
        string="Rad",
        compute="_compute_row_label",
        store=True,
    )
    # True for the synthetic "total" record placed in Jan of year+1
    is_total = fields.Boolean(string="Je súhrn", default=False)
    # Year of the receipt this record belongs to (used for gantt domain filtering)
    receipt_year = fields.Integer(
        string="Rok príjmu",
        compute="_compute_receipt_year",
        store=True,
    )

    @api.depends("project_id")
    def _compute_row_label(self):
        for rec in self:
            rec.row_label = "Príjmy za mesiac"

    @api.depends("receipt_id.year")
    def _compute_receipt_year(self):
        for rec in self:
            rec.receipt_year = rec.receipt_id.year if rec.receipt_id else 0

    @api.depends("date_start")
    def _compute_year_month(self):
        for rec in self:
            if rec.date_start:
                rec.year = rec.date_start.year
                rec.month = rec.date_start.month
            else:
                rec.year = 0
                rec.month = 0

    @api.depends("amount", "currency_id")
    def _compute_name(self):
        for rec in self:
            symbol = rec.currency_id.symbol or ""
            formatted = f"{rec.amount:,.0f}".replace(",", "\u00a0")
            rec.name = f"{formatted}\u00a0{symbol}"

    def write(self, vals):
        vals = dict(vals)
        # Months are fixed — ignore any date changes (gantt drag has no effect)
        vals.pop("date_start", None)
        vals.pop("date_stop", None)
        if not vals:
            return True
        result = super().write(vals)
        if "amount" in vals and not self.env.context.get("_cashflow_adjusting"):
            for receipt in self.mapped("receipt_id"):
                self._adjust_last_month_for_receipt(receipt)
        return result

    def _adjust_last_month_for_receipt(self, receipt):
        # Only consider regular months (not the total summary record)
        all_months = self.search(
            [("receipt_id", "=", receipt.id), ("is_total", "=", False)],
            order="month desc",
        )
        if len(all_months) < 2:
            return
        last = all_months[0]  # December
        others = all_months[1:]
        total_others = sum(others.mapped("amount"))
        last.with_context(_cashflow_adjusting=True).write({
            "amount": receipt.amount - total_others,
        })
