import datetime

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
    cashflow_ids = fields.One2many(
        "tenenet.project.cashflow",
        "receipt_id",
        string="Cashflow",
    )

    @api.depends("date_received")
    def _compute_year(self):
        for rec in self:
            rec.year = rec.date_received.year if rec.date_received else 0

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._generate_equal_cashflow()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "amount" in vals or "date_received" in vals:
            for rec in self:
                rec._generate_equal_cashflow()
        return result

    def _generate_equal_cashflow(self):
        self.ensure_one()
        self.cashflow_ids.unlink()
        if not self.year or not self.amount:
            return
        currency = self.currency_id or self.env.company.currency_id
        monthly_amount = currency.round(self.amount / 12)
        start_month = self.date_received.month if self.date_received else 1
        vals_list = []
        total_assigned = 0.0
        for month in range(start_month, 13):
            date_start = datetime.date(self.year, month, 1)
            if month == start_month:
                date_stop = (
                    datetime.date(self.year, month + 1, 1) - datetime.timedelta(days=1)
                    if month < 12
                    else datetime.date(self.year, 12, 31)
                )
                month_amount = currency.round(monthly_amount * start_month)
                total_assigned += month_amount
            elif month == 12:
                date_stop = datetime.date(self.year, 12, 31)
                month_amount = currency.round(self.amount - total_assigned)
            else:
                date_stop = datetime.date(self.year, month + 1, 1) - datetime.timedelta(days=1)
                month_amount = monthly_amount
                total_assigned += month_amount
            vals_list.append({
                "project_id": self.project_id.id,
                "receipt_id": self.id,
                "date_start": date_start,
                "date_stop": date_stop,
                "amount": month_amount,
            })
        self.env["tenenet.project.cashflow"].create(vals_list)
