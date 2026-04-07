from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TenenetPLProgramOverride(models.Model):
    _name = "tenenet.pl.program.override"
    _description = "P&L override programu"
    _order = "program_label, sequence, row_label, period"

    name = fields.Char(string="Názov", compute="_compute_name", store=True)
    program_id = fields.Many2one("tenenet.program", string="Program", required=True, ondelete="cascade")
    program_label = fields.Char(string="Program", related="program_id.name", store=True, readonly=True)
    period = fields.Date(string="Obdobie", required=True, help="Prvý deň mesiaca.")
    year = fields.Integer(string="Rok", compute="_compute_year_month", store=True)
    month = fields.Integer(string="Mesiac", compute="_compute_year_month", store=True)
    row_key = fields.Char(string="Kľúč riadku", required=True, readonly=True, index=True, default="sales_legacy_unclassified")
    row_label = fields.Char(string="Riadok", required=True, readonly=True, default="Tržby - neklasifikované")
    section_label = fields.Char(string="Sekcia", readonly=True)
    project_label = fields.Char(string="Projekt", readonly=True)
    sequence = fields.Integer(string="Poradie", default=100, readonly=True)
    is_editable = fields.Boolean(string="Upraviteľné", default=True, readonly=True)
    is_separator = fields.Boolean(string="Oddeľovač", default=False, readonly=True)
    amount = fields.Monetary(string="Suma (€)", currency_field="currency_id", default=0.0)
    is_manual = fields.Boolean(string="Manuálne upravené", default=False, readonly=True)
    note = fields.Char(string="Poznámka")
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )

    _unique_program_period_row_key = models.Constraint(
        "UNIQUE(program_id, period, row_key)",
        "Pre rovnaký program, riadok a mesiac môže existovať len jeden P&L override.",
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

    @api.depends("program_id", "period", "row_label")
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
                rec.name = f"{rec.program_label or ''} - {rec.row_label} - {month_names.get(rec.month, '')} {rec.year}".strip(" -")
            else:
                rec.name = f"{rec.program_label or ''} - {rec.row_label}".strip(" -")

    @api.model
    def _normalize_period(self, period):
        return fields.Date.to_date(period).replace(day=1)

    @api.model
    def _grid_reload_action(self):
        return {"type": "ir.actions.client", "tag": "reload"}

    @api.model
    def _with_visible_domain(self, domain=None):
        domain = list(domain or [])
        if not self.env.context.get("include_separators"):
            domain.append(("is_separator", "=", False))
        return domain

    @api.model
    def _auto_sync_grid_year(self):
        if self.env.context.get("_pl_program_override_autosync_done"):
            return
        if not self.env.context.get("auto_sync_pl_program_override"):
            return
        anchor = self.env.context.get("grid_anchor")
        anchor_date = fields.Date.to_date(anchor) if anchor else fields.Date.context_today(self)
        row_specs = self.with_context(
            _pl_program_override_autosync_done=True
        ).env["tenenet.pl.reporting.support"]._get_editable_program_row_specs(anchor_date.year)
        self.with_context(_pl_program_override_autosync_done=True).sync_year_rows(anchor_date.year, row_specs)

    @api.model_create_multi
    def create(self, vals_list):
        normalized_vals_list = []
        for vals in vals_list:
            normalized_vals = dict(vals)
            if normalized_vals.get("period"):
                normalized_vals["period"] = self._normalize_period(normalized_vals["period"])
            normalized_vals_list.append(normalized_vals)
        return super().create(normalized_vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("period"):
            vals["period"] = self._normalize_period(vals["period"])
        if (
            "amount" in vals
            and not self.env.context.get("_pl_program_override_syncing")
            and self.filtered(lambda rec: not rec.is_editable)
        ):
            raise UserError(_("Tento riadok je vypočítaný a nie je možné ho manuálne upravovať."))
        if "amount" in vals and not self.env.context.get("_pl_program_override_syncing"):
            vals["is_manual"] = True
        return super().write(vals)

    @api.model
    def _get_default_row_specs(self):
        selected_year = fields.Date.context_today(self).year
        return self.env["tenenet.pl.reporting.support"]._get_editable_program_row_specs(selected_year)

    @api.model
    def get_year_row_data(self, year):
        result = {}
        records = self.with_context(
            _pl_program_override_autosync_done=True,
            include_separators=True,
        ).search(
            [("year", "=", year)],
            order="program_label, sequence, row_label, period",
        )
        for record in records:
            program_data = result.setdefault(record.program_id.id, {})
            row_data = program_data.setdefault(
                record.row_key,
                {
                    "program_id": record.program_id.id,
                    "program_label": record.program_label or "",
                    "row_key": record.row_key,
                    "row_label": record.row_label,
                    "section_label": record.section_label or "",
                    "project_label": record.project_label or "",
                    "sequence": record.sequence,
                    "is_editable": record.is_editable,
                    "is_separator": record.is_separator,
                    "values": {},
                    "manual_months": {},
                },
            )
            row_data["values"][record.month] = record.amount or 0.0
            row_data["manual_months"][record.month] = bool(record.is_manual)
        return result

    @api.model
    def sync_year_rows(self, year, row_specs=None):
        row_specs = row_specs or self.env["tenenet.pl.reporting.support"]._get_editable_program_row_specs(year)
        sync_self = self.with_context(_pl_program_override_autosync_done=True, include_separators=True)
        existing_records = sync_self.search([("year", "=", year)])
        records_by_key_month = {
            (record.program_id.id, record.row_key, record.month): record
            for record in existing_records
        }
        synced_record_ids = set()
        valid_row_keys = {(row["program_id"], row["row_key"]) for row in row_specs}

        for row in row_specs:
            for month in range(1, 13):
                existing = records_by_key_month.get((row["program_id"], row["row_key"], month))
                values = {
                    "program_id": row["program_id"],
                    "period": date(year, month, 1),
                    "row_key": row["row_key"],
                    "row_label": row["row_label"],
                    "section_label": row.get("section_label") or "",
                    "project_label": row.get("project_label") or "",
                    "sequence": row.get("sequence", 100),
                    "is_editable": row.get("is_editable", True),
                    "is_separator": row.get("is_separator", False),
                    "amount": row.get("values", {}).get(month, existing.amount if existing else 0.0),
                    "currency_id": self.env.company.currency_id.id,
                    "is_manual": False,
                }
                if existing:
                    if existing.is_manual:
                        existing.with_context(_pl_program_override_syncing=True).write({
                            key: value
                            for key, value in values.items()
                            if key not in {"amount", "is_manual"}
                        })
                    else:
                        existing.with_context(_pl_program_override_syncing=True).write(values)
                    synced_record_ids.add(existing.id)
                else:
                    created = sync_self.with_context(_pl_program_override_syncing=True).create(values)
                    synced_record_ids.add(created.id)

        stale_records = existing_records.filtered(
            lambda rec: (rec.program_id.id, rec.row_key) not in valid_row_keys or rec.id not in synced_record_ids
        )
        if stale_records:
            stale_records.unlink()
        return self.browse(sorted(synced_record_ids))

    def action_prepare_grid_year(self):
        anchor = self.env.context.get("grid_anchor")
        anchor_date = fields.Date.to_date(anchor) if anchor else fields.Date.context_today(self)
        row_specs = self.env["tenenet.pl.reporting.support"]._get_editable_program_row_specs(anchor_date.year)
        self.with_context(_pl_program_override_autosync_done=True).sync_year_rows(anchor_date.year, row_specs)
        return False

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        self._auto_sync_grid_year()
        return super().search(self._with_visible_domain(domain), offset=offset, limit=limit, order=order)

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        self._auto_sync_grid_year()
        return super().read_group(
            self._with_visible_domain(domain),
            fields,
            groupby,
            offset=offset,
            limit=limit,
            orderby=orderby,
            lazy=lazy,
        )
