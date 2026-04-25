from datetime import date

from odoo import api, fields, models
from odoo.fields import Domain


class TenenetCashflowGlobalOverride(models.Model):
    _name = "tenenet.cashflow.global.override"
    _description = "Globálny cashflow override"
    _order = "sequence, row_label, period"

    name = fields.Char(
        string="Názov",
        compute="_compute_name",
        store=True,
    )
    period = fields.Date(
        string="Obdobie",
        required=True,
        help="Prvý deň mesiaca.",
    )
    year = fields.Integer(
        string="Rok",
        compute="_compute_year_month",
        store=True,
    )
    month = fields.Integer(
        string="Mesiac",
        compute="_compute_year_month",
        store=True,
    )
    row_key = fields.Char(
        string="Kľúč riadku",
        required=True,
        index=True,
        readonly=True,
        default="legacy:cash_in",
    )
    row_label = fields.Char(
        string="Riadok",
        required=True,
        default="Cash-IN",
    )
    row_type = fields.Selection(
        [
            ("income", "Cash-IN detail"),
            ("salary", "Mzdy"),
            ("expense", "Cash-OUT detail"),
        ],
        string="Typ riadku",
        required=True,
        readonly=True,
        default="income",
    )
    section_label = fields.Char(string="Sekcia", readonly=True)
    program_label = fields.Char(string="Program", readonly=True)
    project_label = fields.Char(string="Projekt", readonly=True)
    sequence = fields.Integer(string="Poradie", default=100, readonly=True)
    amount = fields.Monetary(
        string="Suma (€)",
        currency_field="currency_id",
        default=0.0,
    )
    source_kind = fields.Selection(
        [
            ("forecast", "Forecast"),
            ("workbook", "Workbook"),
            ("workbook_actual", "Workbook + skutočnosť"),
            ("manual", "Manual"),
        ],
        string="Zdroj",
        default="forecast",
        readonly=True,
    )
    source_sheet = fields.Char(string="Zdrojový hárok", readonly=True)
    source_row = fields.Integer(string="Zdrojový riadok", readonly=True)
    actual_mapping_key = fields.Char(
        string="Mapovanie skutočnosti",
        readonly=True,
        help="Technický kľúč použitý na nahradenie plánovanej hodnoty skutočnosťou.",
    )
    note = fields.Char(string="Poznámka")
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )

    _unique_period_row_key = models.Constraint(
        "UNIQUE(period, row_key)",
        "Pre rovnaký riadok a mesiac môže existovať len jeden cashflow override.",
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

    @api.depends("period", "row_label")
    def _compute_name(self):
        month_names = {
            1: "Január",
            2: "Február",
            3: "Marec",
            4: "Apríl",
            5: "Máj",
            6: "Jún",
            7: "Júl",
            8: "August",
            9: "September",
            10: "Október",
            11: "November",
            12: "December",
        }
        for rec in self:
            if rec.period:
                rec.name = f"{rec.row_label} - {month_names.get(rec.month, '')} {rec.year}".strip()
            else:
                rec.name = rec.row_label or ""

    @api.model
    def _normalize_period(self, period):
        return fields.Date.to_date(period).replace(day=1)

    @api.model
    def _grid_reload_action(self):
        return {"type": "ir.actions.client", "tag": "reload"}

    @api.model
    def _auto_sync_grid_year(self):
        if self.env.context.get("_cashflow_override_autosync_done"):
            return
        if not self.env.context.get("auto_sync_cashflow_override"):
            return
        anchor = self.env.context.get("grid_anchor")
        anchor_date = fields.Date.to_date(anchor) if anchor else fields.Date.context_today(self)
        row_specs = self.with_context(
            _cashflow_override_autosync_done=True
        ).env["tenenet.cashflow.report.handler"]._get_effective_editable_rows(anchor_date.year)
        self.with_context(_cashflow_override_autosync_done=True).sync_year_rows(anchor_date.year, row_specs)

    @api.model_create_multi
    def create(self, vals_list):
        normalized_vals_list = []
        for vals in vals_list:
            normalized_vals = dict(vals)
            if normalized_vals.get("period"):
                normalized_vals["period"] = self._normalize_period(normalized_vals["period"])
            normalized_vals_list.append(normalized_vals)
        records = super().create(normalized_vals_list)
        if not self.env.context.get("_cashflow_override_adjusting"):
            for row_key, year in {(rec.row_key, rec.year) for rec in records.filtered(lambda rec: rec.row_type == "income")}:
                self._adjust_last_income_month(row_key, year)
        if not self.env.context.get("_skip_finance_monthly_comparison_sync"):
            self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs(
                self._finance_monthly_comparison_pairs_from_rows(records)
            )
        return records

    def write(self, vals):
        old_pairs = self._finance_monthly_comparison_pairs_from_rows(self)
        vals = dict(vals)
        if vals.get("period"):
            vals["period"] = self._normalize_period(vals["period"])
        result = super().write(vals)
        if "amount" in vals and not self.env.context.get("_cashflow_override_adjusting"):
            for row_key, year in {(rec.row_key, rec.year) for rec in self.filtered(lambda rec: rec.row_type == "income")}:
                self._adjust_last_income_month(row_key, year)
        if not self.env.context.get("_skip_finance_monthly_comparison_sync"):
            self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs(
                old_pairs | self._finance_monthly_comparison_pairs_from_rows(self)
            )
        return result

    @api.model
    def _get_income_forecast_target(self, row_key, year):
        if not row_key.startswith("income:"):
            return 0.0, False
        try:
            project_id = int(row_key.split(":", 1)[1])
        except (TypeError, ValueError):
            return 0.0, False
        cashflows = self.env["tenenet.project.cashflow"].search(
            [("project_id", "=", project_id), ("receipt_year", "=", year)],
            order="month desc",
        )
        if not cashflows:
            return 0.0, False
        return sum(cashflows.mapped("amount")), cashflows[0].month

    def _adjust_last_income_month(self, row_key, year):
        target_total, last_month = self._get_income_forecast_target(row_key, year)
        if not last_month:
            return
        year_rows = self.search(
            [("year", "=", year), ("row_key", "=", row_key)],
            order="month desc",
        )
        if not year_rows:
            return
        last_row = year_rows.filtered(lambda rec: rec.month == last_month)[:1]
        if not last_row:
            last_row = year_rows[0]
        other_rows = year_rows - last_row
        last_row.with_context(_cashflow_override_adjusting=True).write({
            "amount": target_total - sum(other_rows.mapped("amount")),
        })

    @api.model
    def get_year_row_data(self, year):
        result = {}
        records = self.search(
            [("year", "=", year), ("row_key", "!=", "legacy:cash_in")],
            order="sequence, row_label, period",
        )
        for record in records:
            row_data = result.setdefault(
                record.row_key,
                {
                    "row_key": record.row_key,
                    "row_label": record.row_label,
                    "row_type": record.row_type,
                    "section_label": record.section_label or "",
                    "program": record.program_label or "",
                    "project_label": record.project_label or record.row_label,
                    "sequence": record.sequence,
                    "source_kind": record.source_kind or "forecast",
                    "source_sheet": record.source_sheet or "",
                    "source_row": record.source_row or 0,
                    "actual_mapping_key": record.actual_mapping_key or "",
                    "values": {},
                },
            )
            row_data["values"][record.month] = record.amount or 0.0
        return result

    @api.model
    def sync_year_rows(self, year, row_specs):
        existing_records = self.search([("year", "=", year)])
        legacy_records = existing_records.filtered(lambda rec: rec.row_key == "legacy:cash_in")
        if legacy_records:
            legacy_records.unlink()
        existing_records -= legacy_records
        valid_row_keys = {row["row_key"] for row in row_specs}
        records_by_key_month = {
            (record.row_key, record.month): record
            for record in existing_records
        }
        synced_record_ids = set()

        for row in row_specs:
            for month in range(1, 13):
                values = {
                    "period": date(year, month, 1),
                    "row_key": row["row_key"],
                    "row_label": row["row_label"],
                    "row_type": row["row_type"],
                    "section_label": row.get("section_label") or "",
                    "program_label": row.get("program") or "",
                    "project_label": row.get("project_label") or row["row_label"],
                    "sequence": row.get("sequence", 100),
                    "amount": row["values"].get(month, 0.0),
                    "currency_id": self.env.company.currency_id.id,
                    "source_kind": row.get("source_kind") or "forecast",
                    "source_sheet": row.get("source_sheet") or "",
                    "source_row": row.get("source_row") or 0,
                    "actual_mapping_key": row.get("actual_mapping_key") or row["row_key"],
                }
                existing = records_by_key_month.get((row["row_key"], month))
                if existing:
                    if existing.source_kind == "workbook" and row.get("source_kind") == "workbook_actual":
                        values["amount"] = existing.amount
                        values["source_kind"] = "workbook"
                    existing.with_context(
                        _cashflow_override_adjusting=True,
                        _skip_finance_monthly_comparison_sync=True,
                    ).write(values)
                    synced_record_ids.add(existing.id)
                else:
                    created = self.with_context(
                        _cashflow_override_adjusting=True,
                        _skip_finance_monthly_comparison_sync=True,
                    ).create(values)
                    synced_record_ids.add(created.id)

        stale_records = existing_records.filtered(
            lambda rec: (
                (rec.row_key not in valid_row_keys or rec.id not in synced_record_ids)
                and rec.source_kind != "workbook"
            )
        )
        if stale_records:
            stale_records.with_context(_skip_finance_monthly_comparison_sync=True).unlink()
        return self.browse(sorted(synced_record_ids))

    def action_prepare_grid_year(self):
        anchor = self.env.context.get("grid_anchor")
        anchor_date = fields.Date.to_date(anchor) if anchor else fields.Date.context_today(self)
        row_specs = self.env["tenenet.cashflow.report.handler"]._get_effective_editable_rows(anchor_date.year)
        self.sync_year_rows(anchor_date.year, row_specs)
        return False

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        self._auto_sync_grid_year()
        return super().search(domain, offset=offset, limit=limit, order=order)

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        self._auto_sync_grid_year()
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
    def grid_update_cell(self, domain, measure_field_name, value):
        if measure_field_name != "amount" or value == 0:
            return super().grid_update_cell(domain, measure_field_name, value)

        record = self.search(Domain.AND([domain]), limit=1)
        if record:
            record.amount = (record.amount or 0.0) + value
            return self._grid_reload_action()

        period = None
        row_label = None
        project_label = None
        for token in domain:
            if not isinstance(token, (list, tuple)) or len(token) != 3:
                continue
            if token[0] == "period" and token[1] == "=":
                period = token[2]
            elif token[0] == "row_label" and token[1] == "=":
                row_label = token[2]
            elif token[0] == "project_label" and token[1] == "=":
                project_label = token[2]
        row_identifier = project_label or row_label
        if not period or not row_identifier:
            return False

        period = self._normalize_period(period)
        template = self.search(
            [("year", "=", period.year), ("project_label", "=", row_identifier)],
            limit=1,
        )
        if not template:
            return False

        self.create({
            "period": period,
            "row_key": template.row_key,
            "row_label": template.row_label,
            "row_type": template.row_type,
            "section_label": template.section_label,
            "program_label": template.program_label,
            "project_label": template.project_label,
            "sequence": template.sequence,
            "amount": value,
            "currency_id": template.currency_id.id,
        })
        return self._grid_reload_action()

    @api.model
    def _finance_monthly_comparison_pairs_from_rows(self, rows):
        pairs = set()
        for record in rows.filtered(lambda rec: rec.row_type == "income" and rec.row_key):
            if not record.row_key.startswith("income:"):
                continue
            try:
                project_id = int(record.row_key.split(":", 1)[1])
            except (TypeError, ValueError):
                continue
            if project_id and record.year:
                pairs.add((project_id, record.year))
        return pairs

    def unlink(self):
        pairs = self._finance_monthly_comparison_pairs_from_rows(self)
        result = super().unlink()
        if not self.env.context.get("_skip_finance_monthly_comparison_sync"):
            self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs(pairs)
        return result
