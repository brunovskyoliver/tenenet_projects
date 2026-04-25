import datetime

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


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

    def _get_min_cashflow_month(self):
        self.ensure_one()
        return self.date_received.month if self.date_received else 1

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

    def action_delete_with_reload(self):
        self.ensure_one()
        self.unlink()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)

    def write(self, vals):
        old_pairs = {
            (record.project_id.id, record.year)
            for record in self
            if record.project_id and record.year
        }
        had_cashflow = {record.id: bool(record.cashflow_ids) for record in self}
        result = super().write(vals)
        if (
            ("amount" in vals or "date_received" in vals)
            and not self.env.context.get("skip_tenenet_receipt_auto_cashflow")
        ):
            for rec in self:
                if had_cashflow.get(rec.id):
                    rec._generate_equal_cashflow()
            self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs(
                old_pairs | {
                    (record.project_id.id, record.year)
                    for record in self
                    if record.project_id and record.year
                }
            )
        return result

    def _generate_equal_cashflow(self):
        self.ensure_one()
        if not self.year or not self.amount:
            self.cashflow_ids.unlink()
            return
        start_month = self.date_received.month if self.date_received else 1
        month_numbers = list(range(start_month, 13))
        currency = self.currency_id or self.env.company.currency_id
        monthly_amount = currency.round(self.amount / len(month_numbers))
        assigned_amount = 0.0
        month_amounts = {}
        for index, month in enumerate(month_numbers, start=1):
            if index == len(month_numbers):
                month_amounts[month] = currency.round(self.amount - assigned_amount)
            else:
                month_amounts[month] = monthly_amount
                assigned_amount += monthly_amount
        self._replace_cashflow_month_amounts(month_amounts)

    def _replace_cashflow_month_amounts(self, month_amounts):
        self.ensure_one()
        min_month = self._get_min_cashflow_month()
        invalid_months = [month for month in month_amounts if int(month) < min_month]
        if invalid_months:
            raise ValidationError(
                "Cashflow nemôže začínať pred mesiacom prijatia príjmu."
            )
        self.cashflow_ids.unlink()
        if not month_amounts:
            return True

        values_list = []
        for month in sorted(month_amounts):
            if abs(month_amounts[month]) < 0.00001:
                continue
            date_start, date_stop = self._month_bounds(self.year, month)
            values_list.append({
                "project_id": self.project_id.id,
                "receipt_id": self.id,
                "date_start": date_start,
                "date_stop": date_stop,
                "amount": month_amounts[month],
            })
        self.env["tenenet.project.cashflow"].create(values_list)
        return True

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
        if date_from.month < self._get_min_cashflow_month():
            raise ValidationError("Cashflow nemôže začínať pred mesiacom prijatia príjmu.")

        total_amount = amount if amount is not None else self.amount
        currency = self.currency_id or self.env.company.currency_id
        month_numbers = self._iter_month_numbers(date_from, date_to)

        if not total_amount or not month_numbers:
            self.cashflow_ids.unlink()
            return True

        monthly_amount = currency.round(total_amount / len(month_numbers))
        assigned_amount = 0.0
        month_amounts = {}
        for index, month in enumerate(month_numbers, start=1):
            if index == len(month_numbers):
                month_amount = currency.round(total_amount - assigned_amount)
            else:
                month_amount = monthly_amount
                assigned_amount += month_amount
            month_amounts[month] = month_amount
        return self._replace_cashflow_month_amounts(month_amounts)

    def distribute_cashflow_month_span(self, year, start_month, end_month):
        self.ensure_one()
        year = int(year or 0)
        start_month = int(start_month or 0)
        end_month = int(end_month or 0)
        if year != self.year:
            raise ValidationError("Vybraný rok musí byť zhodný s rokom príjmu.")
        if start_month < 1 or start_month > 12 or end_month < 1 or end_month > 12:
            raise ValidationError("Mesiace distribúcie musia byť v rozsahu 1 až 12.")
        if start_month > end_month:
            raise ValidationError("Počiatočný mesiac nemôže byť neskôr ako koncový mesiac.")

        date_from, _date_ignore = self._month_bounds(year, start_month)
        _date_ignore, date_to = self._month_bounds(year, end_month)
        return self.distribute_cashflow_span(date_from, date_to)

    def set_cashflow_month_amounts(self, year, month_amounts):
        self.ensure_one()
        year = int(year or 0)
        if year != self.year:
            raise ValidationError("Vybraný rok musí byť zhodný s rokom príjmu.")
        if not isinstance(month_amounts, dict) or not month_amounts:
            raise ValidationError("Je potrebné zadať aspoň jeden mesiac cashflow.")

        currency = self.currency_id or self.env.company.currency_id
        min_month = self._get_min_cashflow_month()
        normalized_amounts = {}
        for month_key, amount in month_amounts.items():
            month = int(month_key)
            if month < 1 or month > 12:
                raise ValidationError("Mesiace cashflow musia byť v rozsahu 1 až 12.")
            amount_value = currency.round(float(amount or 0.0))
            if month < min_month:
                if abs(amount_value) < 0.00001:
                    continue
                raise ValidationError("Cashflow nemôže začínať pred mesiacom prijatia príjmu.")
            if amount_value < 0:
                raise ValidationError("Mesačný cashflow nemôže byť záporný.")
            normalized_amounts[month] = amount_value

        total_amount = sum(normalized_amounts.values())
        if float_compare(total_amount, self.amount, precision_rounding=currency.rounding) > 0:
            raise ValidationError("Súčet mesačných hodnôt nemôže byť vyšší ako celá suma príjmu.")

        return self._replace_cashflow_month_amounts(normalized_amounts)

    def planner_set_cashflow_month_amounts(self, year, month_amounts):
        self.ensure_one()
        result = self.set_cashflow_month_amounts(year, month_amounts)
        currency = self.currency_id or self.env.company.currency_id
        total_amount = sum((self.cashflow_ids or self.env["tenenet.project.cashflow"]).mapped("amount"))
        if float_compare(total_amount, self.amount, precision_rounding=currency.rounding) != 0:
            raise ValidationError("Pri uložení planneru musí byť rozdelená celá suma príjmu.")
        return result

    def unlink(self):
        affected_pairs = {
            (record.project_id.id, record.year)
            for record in self
            if record.project_id and record.year
        }
        result = super().unlink()
        self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs(affected_pairs)
        return result
