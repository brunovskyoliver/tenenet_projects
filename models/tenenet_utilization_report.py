from odoo import fields, models
from odoo.tools import format_date


class TenenetUtilizationReportHandler(models.AbstractModel):
    _name = "tenenet.utilization.report.handler"
    _inherit = ["account.report.custom.handler"]
    _description = "TENENET Utilization Report Handler"

    _PERCENTAGE_COLUMNS = {"utilization_rate", "non_project_rate"}
    _FLOAT_COLUMNS = {
        "work_ratio",
        "capacity_hours",
        "leaves_kpi_hours",
        "hours_pp",
        "hours_np",
        "hours_travel",
        "hours_training",
        "hours_ambulance",
        "hours_international",
        "hours_project_total",
        "hours_vacation",
        "hours_doctor",
        "hours_sick",
        "hours_holidays",
        "hours_ballast",
        "hours_non_project_total",
        "hours_diff",
    }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        custom_display_config = options["custom_display_config"]
        custom_display_config["css_custom_class"] = (
            custom_display_config.get("css_custom_class", "") + " tenenet_utilization_report"
        ).strip()
        custom_display_config.setdefault("components", {})["AccountReportFilters"] = "TenenetUtilizationReportFilters"

        period = self._get_selected_month_start(report, options)
        options["date"]["filter"] = "this_month"
        options["date"]["period_type"] = "month"
        options["date"]["period"] = self._get_month_offset(period)
        options["date"]["date_from"] = fields.Date.to_string(period)
        options["date"]["date_to"] = fields.Date.to_string(fields.Date.end_of(period, "month"))
        month_str = format_date(self.env, options["date"]["date_to"], date_format="MMM yyyy")
        options["date"]["string"] = month_str

        # Fix the column group header — Odoo builds it from raw dates ("Od DD/MM/YYYY"),
        # so we overwrite the string after the column groups are already populated.
        for cg_data in options.get("column_groups", {}).values():
            if isinstance(cg_data, dict):
                cg_data["string"] = month_str

        # Warning filter: persist toggle across report reloads via previous_options
        options["tenenet_filter_warnings"] = (
            previous_options.get("tenenet_filter_warnings", False)
            if previous_options
            else False
        )

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        period = self._get_selected_month_start(report, options)
        utilization_records = self.env["tenenet.utilization"].sudo()._sync_for_period(period)
        # Force a fresh recompute so the report always shows live data even when leaves
        # or project assignments have been deleted since the records were last computed.
        utilization_records._compute_from_timesheets()
        utilization_records = self._get_utilization_records(
            period,
            search_term=options.get("filter_search_bar"),
            only_warnings=options.get("tenenet_filter_warnings", False),
        )
        return [
            (0, self._get_report_line(report, options, utilization))
            for utilization in utilization_records
        ]

    def _get_selected_month_start(self, report, options):
        date_to = options.get("date", {}).get("date_to") or fields.Date.context_today(self)
        return self.env["tenenet.utilization"]._normalize_period(date_to)

    def _get_month_offset(self, period):
        period_date = fields.Date.to_date(period)
        today = fields.Date.context_today(self)
        today_month_start = today.replace(day=1)
        return (period_date.year - today_month_start.year) * 12 + period_date.month - today_month_start.month

    def _get_utilization_records(self, period, search_term=None, only_warnings=False):
        records = self.env["tenenet.utilization"].search([("period", "=", period)])
        if search_term:
            lowered_search_term = search_term.lower()
            records = records.filtered(
                lambda rec: lowered_search_term in (rec.employee_id.name or "").lower()
                or lowered_search_term in (rec.manager_name or "").lower()
            )
        if only_warnings:
            records = records.filtered(
                lambda rec: rec.utilization_status == "warning" or rec.non_project_status == "warning"
            )
        return records.sorted(
            key=lambda rec: (
                (rec.manager_name or "").lower(),
                (rec.employee_id.name or "").lower(),
                rec.employee_id.id,
            )
        )

    def _get_report_line(self, report, options, utilization):
        columns = []
        for column in options["columns"]:
            label = column["expression_label"]
            columns.append(
                report._build_column_dict(
                    self._get_column_value(utilization, label),
                    column,
                    options=options,
                    digits=2,
                )
            )

        return {
            "id": report._get_generic_line_id("hr.employee", utilization.employee_id.id, markup="tenenet_utilization"),
            "name": utilization.employee_id.name or "",
            "columns": columns,
            "level": 2,
        }

    def _get_column_value(self, utilization, label):
        if label == "manager_name":
            return utilization.manager_name or ""
        return utilization[label]
