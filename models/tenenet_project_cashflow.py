from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
    section_label = fields.Char(string="Sekcia", readonly=True)
    project_label = fields.Char(string="Projekt", readonly=True)
    receipt_label = fields.Char(string="Príjem", readonly=True)
    receipt_year = fields.Integer(
        string="Rok príjmu",
        compute="_compute_receipt_year",
        store=True,
    )

    @api.depends("project_id")
    def _compute_row_label(self):
        for rec in self:
            rec.row_label = "Príjmy za mesiac"

    @api.model
    def _format_sk_date(self, value):
        date_value = fields.Date.to_date(value)
        if not date_value:
            return ""
        return f"{date_value.day}.{date_value.month}.{date_value.year}"

    @api.model
    def _format_sk_amount(self, value):
        amount = value or 0.0
        if abs(amount - round(amount)) < 0.00001:
            formatted = f"{int(round(amount)):,}".replace(",", " ")
        else:
            formatted = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
        return f"{formatted} €"

    def _get_grid_label_values(self):
        self.ensure_one()
        values = {
            "section_label": "Príjmy",
            "project_label": self.project_id.display_name or "",
            "receipt_label": "",
        }
        if self.receipt_id:
            receipt_date = self._format_sk_date(self.receipt_id.date_received)
            receipt_amount = self._format_sk_amount(self.receipt_id.amount)
            values["receipt_label"] = f"{receipt_date} / {receipt_amount}"
        return values

    def _sync_grid_labels(self):
        for rec in self:
            values = rec._get_grid_label_values()
            changed_values = {
                field_name: value
                for field_name, value in values.items()
                if rec[field_name] != value
            }
            if changed_values:
                super(TenenetProjectCashflow, rec.with_context(_cashflow_label_syncing=True)).write(changed_values)

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

    @api.constrains("receipt_id", "date_start")
    def _check_receipt_month_alignment(self):
        for rec in self:
            if not rec.receipt_id or not rec.date_start:
                continue
            receipt_date = rec.receipt_id.date_received
            if not receipt_date:
                continue
            if rec.date_start.year != receipt_date.year:
                raise ValidationError("Cashflow musí zostať v rovnakom roku ako prijatý príjem.")
            if rec.date_start.month < receipt_date.month:
                raise ValidationError("Cashflow nemôže začínať pred mesiacom prijatia príjmu.")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_grid_labels()
        self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs({
            (record.project_id.id, record.receipt_year)
            for record in records
            if record.project_id and record.receipt_year
        })
        return records

    def write(self, vals):
        old_pairs = {
            (record.project_id.id, record.receipt_year)
            for record in self
            if record.project_id and record.receipt_year
        }
        vals = dict(vals)
        # Months are fixed — ignore any date changes (gantt drag has no effect)
        vals.pop("date_start", None)
        vals.pop("date_stop", None)
        if not vals:
            return True
        result = super().write(vals)
        if not self.env.context.get("_cashflow_label_syncing"):
            self._sync_grid_labels()
        if "amount" in vals and not self.env.context.get("_cashflow_adjusting"):
            for receipt in self.mapped("receipt_id"):
                self._adjust_last_month_for_receipt(receipt)
        self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs(
            old_pairs | {
                (record.project_id.id, record.receipt_year)
                for record in self
                if record.project_id and record.receipt_year
            }
        )
        return result

    @api.model
    def _refresh_grid_labels_for_domain(self, domain=None):
        if self.env.context.get("_cashflow_label_syncing") or not self.env.context.get("auto_sync_project_cashflow_labels"):
            return
        records = super(TenenetProjectCashflow, self).search(domain or [])
        records._sync_grid_labels()

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        self._refresh_grid_labels_for_domain(domain)
        return super().search(domain, offset=offset, limit=limit, order=order)

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        self._refresh_grid_labels_for_domain(domain)
        return super().read_group(
            domain,
            fields,
            groupby,
            offset=offset,
            limit=limit,
            orderby=orderby,
            lazy=lazy,
        )

    @api.model
    def _grid_reload_action(self):
        return {"type": "ir.actions.client", "tag": "reload"}

    @api.model
    def grid_update_cell(self, domain, measure_field_name, value):
        if measure_field_name != "amount" or value == 0:
            return super().grid_update_cell(domain, measure_field_name, value)
        record = self.search(domain, limit=1)
        if not record:
            return False
        record.amount = (record.amount or 0.0) + value
        return self._grid_reload_action()

    def _adjust_last_month_for_receipt(self, receipt):
        all_months = self.search(
            [("receipt_id", "=", receipt.id)],
            order="month desc",
        )
        if not all_months:
            return
        currency = receipt.currency_id or self.env.company.currency_id
        if len(all_months) == 1:
            all_months.with_context(_cashflow_adjusting=True).write({"amount": currency.round(receipt.amount)})
            return
        last = all_months[0]
        others = all_months[1:]
        total_others = sum(others.mapped("amount"))
        last.with_context(_cashflow_adjusting=True).write({
            "amount": currency.round(receipt.amount - total_others),
        })

    def unlink(self):
        affected_years = set(self.mapped("receipt_year"))
        affected_pairs = {
            (record.project_id.id, record.receipt_year)
            for record in self
            if record.project_id and record.receipt_year
        }
        result = super().unlink()
        if affected_years:
            handler = self.env["tenenet.cashflow.report.handler"]
            override_model = self.env["tenenet.cashflow.global.override"]
            for year in affected_years:
                override_model.sync_year_rows(year, handler._get_effective_editable_rows(year, {}))
        self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs(affected_pairs)
        return result
