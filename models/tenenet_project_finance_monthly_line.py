from datetime import date

from odoo import api, fields, models


class TenenetProjectFinanceMonthlyLine(models.Model):
    _name = "tenenet.project.finance.monthly.line"
    _description = "Mesačné porovnanie cashflow a výdavkov projektu"
    _order = "period asc, series"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
        index=True,
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
    series = fields.Selection(
        [
            ("predicted_cf", "Predikovaný CF"),
            ("real_expense", "Reálne výdavky"),
        ],
        string="Séria",
        required=True,
    )
    amount = fields.Monetary(
        string="Suma",
        currency_field="currency_id",
        default=0.0,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="project_id.currency_id",
        store=True,
        readonly=True,
    )

    _unique_project_period_series = models.Constraint(
        "UNIQUE(project_id, period, series)",
        "Pre rovnaký projekt, mesiac a sériu môže existovať len jeden riadok.",
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

    @api.model
    def _series_amount_map_for_project_year(self, project, year):
        predicted_values = project._get_effective_cashflow_month_values(year)
        return {
            "predicted_cf": {
                month: predicted_values.get(month, 0.0)
                for month in range(1, 13)
            },
            "real_expense": {
                month: project._get_actual_project_spend_for_month(year, month)
                for month in range(1, 13)
            },
        }

    @api.model
    def sync_project_year(self, project, year):
        if not project or not project.exists():
            return self.browse()

        year = int(year or 0)
        if not year:
            return self.browse()

        existing_records = self.search([
            ("project_id", "=", project.id),
            ("year", "=", year),
        ])
        existing_by_key = {
            (record.month, record.series): record
            for record in existing_records
        }
        series_amounts = self._series_amount_map_for_project_year(project, year)
        synced_ids = []

        for series, month_amounts in series_amounts.items():
            for month in range(1, 13):
                values = {
                    "project_id": project.id,
                    "period": date(year, month, 1),
                    "series": series,
                    "amount": month_amounts.get(month, 0.0),
                }
                existing = existing_by_key.get((month, series))
                if existing:
                    existing.write(values)
                    synced_ids.append(existing.id)
                else:
                    synced_ids.append(self.create(values).id)

        stale_records = existing_records.filtered(lambda rec: rec.id not in synced_ids)
        if stale_records:
            stale_records.unlink()
        return self.browse(synced_ids)
