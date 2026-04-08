import datetime

from odoo import api, fields, models
from odoo.exceptions import ValidationError


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

    @api.model
    def _month_bounds(self, year, month):
        date_start = datetime.date(year, month, 1)
        if month == 12:
            date_stop = datetime.date(year, 12, 31)
        else:
            date_stop = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
        return date_start, date_stop

    @api.model
    def _iter_month_numbers(self, date_from, date_to):
        current = fields.Date.to_date(date_from).replace(day=1)
        end = fields.Date.to_date(date_to).replace(day=1)
        months = []
        while current <= end:
            months.append(current.month)
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        return months

    def action_open_cashflow_distribute_wizard(self):
        self.ensure_one()
        return {
            "name": "Distribuovať cashflow",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.cashflow.distribute.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_receipt_id": self.id},
        }

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

    def distribute_cashflow_span(self, date_from, date_to, amount=None):
        self.ensure_one()
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if not self.year:
            raise ValidationError("Príjem musí mať nastavený rok pred distribúciou cashflow.")
        if not date_from or not date_to:
            raise ValidationError("Je potrebné zadať obdobie distribúcie cashflow.")
        if date_from > date_to:
            raise ValidationError("Dátum od nemôže byť neskôr ako dátum do.")
        if date_from.year != self.year or date_to.year != self.year:
            raise ValidationError("Distribúcia cashflow musí zostať v roku príjmu.")

        total_amount = amount if amount is not None else self.amount
        currency = self.currency_id or self.env.company.currency_id
        month_numbers = self._iter_month_numbers(date_from, date_to)

        self.cashflow_ids.unlink()
        if not total_amount or not month_numbers:
            return True

        monthly_amount = currency.round(total_amount / len(month_numbers))
        assigned_amount = 0.0
        values_list = []
        for index, month in enumerate(month_numbers, start=1):
            date_start, date_stop = self._month_bounds(self.year, month)
            if index == len(month_numbers):
                month_amount = currency.round(total_amount - assigned_amount)
            else:
                month_amount = monthly_amount
                assigned_amount += month_amount
            values_list.append({
                "project_id": self.project_id.id,
                "receipt_id": self.id,
                "date_start": date_start,
                "date_stop": date_stop,
                "amount": month_amount,
            })
        self.env["tenenet.project.cashflow"].create(values_list)
        return True
