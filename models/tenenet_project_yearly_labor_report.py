from collections import defaultdict
from datetime import date

from odoo import fields, models


MONTH_COLUMN_LABELS = {
    1: "month_01",
    2: "month_02",
    3: "month_03",
    4: "month_04",
    5: "month_05",
    6: "month_06",
    7: "month_07",
    8: "month_08",
    9: "month_09",
    10: "month_10",
    11: "month_11",
    12: "month_12",
}


class TenenetProjectYearlyLaborReportHandler(models.AbstractModel):
    _name = "tenenet.project.yearly.labor.report.handler"
    _inherit = ["account.report.custom.handler"]
    _description = "TENENET Project Yearly Labor Report Handler"

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        custom_display_config = options["custom_display_config"]
        custom_display_config["css_custom_class"] = (
            custom_display_config.get("css_custom_class", "") + " tenenet_project_yearly_labor_report"
        ).strip()
        custom_display_config.setdefault("components", {})["AccountReportFilters"] = (
            "TenenetProjectYearlyLaborReportFilters"
        )

        selected_project = self._get_selected_project_from_options(previous_options)
        options["project_ids"] = [selected_project.id] if selected_project else []
        options["selected_project_name"] = selected_project.display_name if selected_project else "Projekt"

        selected_year = self._get_selected_year(options)
        self._set_year_options(options, selected_year)

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        project = self._get_selected_project_from_options(options)
        if not project:
            return []

        selected_year = self._get_selected_year(options)
        timesheets = self._get_project_year_timesheets(project, selected_year)
        if not timesheets:
            return []

        employee_buckets = self._group_timesheets_by_employee(timesheets)
        lines = []
        total_hours_by_month = defaultdict(float)
        total_amount_by_month = defaultdict(float)

        sorted_employee_rows = sorted(
            employee_buckets.values(),
            key=lambda bucket: (bucket["employee"].name or "").lower(),
        )
        for employee_bucket in sorted_employee_rows:
            employee = employee_bucket["employee"]
            lines.append((0, self._build_employee_metric_line(report, options, employee, employee_bucket, "amount")))
            lines.append((0, self._build_employee_metric_line(report, options, employee, employee_bucket, "hours")))

            for month_index in range(1, 13):
                total_hours_by_month[month_index] += employee_bucket["hours"][month_index]
                total_amount_by_month[month_index] += employee_bucket["amount"][month_index]

        lines.append((0, self._build_total_line(report, options, "Hodiny spolu", total_hours_by_month, "float")))
        lines.append((0, self._build_total_line(report, options, "Suma spolu", total_amount_by_month, "monetary")))
        return lines

    def _get_selected_project_from_options(self, options):
        project_ids = (options or {}).get("project_ids") or []
        project_id = project_ids[:1]
        if project_id:
            return self.env["tenenet.project"].with_context(active_test=False).browse(project_id[0]).exists()
        return self._get_default_project()

    def _get_default_project(self):
        Timesheet = self.env["tenenet.project.timesheet"].with_context(active_test=False)
        first_timesheet = Timesheet.search([], order="project_id, employee_id, period", limit=1)
        if first_timesheet:
            return first_timesheet.project_id
        return self.env["tenenet.project"].with_context(active_test=False).search([], order="name", limit=1)

    def _get_selected_year(self, options):
        date_to = options.get("date", {}).get("date_to") or fields.Date.context_today(self)
        return fields.Date.to_date(date_to).year

    def _set_year_options(self, options, selected_year):
        today_year = fields.Date.context_today(self).year
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)

        options["date"]["filter"] = "this_year"
        options["date"]["period_type"] = "year"
        options["date"]["period"] = selected_year - today_year
        options["date"]["date_from"] = fields.Date.to_string(year_start)
        options["date"]["date_to"] = fields.Date.to_string(year_end)
        options["date"]["string"] = str(selected_year)

    def _get_project_year_timesheets(self, project, selected_year):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        return self.env["tenenet.project.timesheet"].search(
            [
                ("project_id", "=", project.id),
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ],
            order="employee_id, period",
        )

    def _group_timesheets_by_employee(self, timesheets):
        employee_buckets = {}
        for timesheet in timesheets:
            employee = timesheet.employee_id
            if employee.id not in employee_buckets:
                employee_buckets[employee.id] = {
                    "employee": employee,
                    "hours": defaultdict(float),
                    "amount": defaultdict(float),
                }
            employee_buckets[employee.id]["hours"][timesheet.period.month] += timesheet.hours_total or 0.0
            employee_buckets[employee.id]["amount"][timesheet.period.month] += timesheet.total_labor_cost or 0.0
        return employee_buckets

    def _build_employee_metric_line(self, report, options, employee, monthly_values, metric_type):
        metric_name = "Celková cena práce" if metric_type == "amount" else "Odpracované hodiny"
        figure_type = "monetary" if metric_type == "amount" else "float"
        values = monthly_values[metric_type]
        return {
            "id": report._get_generic_line_id(
                "hr.employee",
                employee.id,
                markup=f"project_yearly_labor_{metric_type}",
            ),
            "name": employee.name or "",
            "columns": self._build_metric_columns(report, options, metric_name, values, figure_type),
            "level": 2,
        }

    def _build_total_line(self, report, options, line_name, monthly_values, figure_type):
        return {
            "id": report._get_generic_line_id(
                None,
                None,
                markup=f"project_yearly_labor_total_{line_name.replace(' ', '_').lower()}",
            ),
            "name": line_name,
            "columns": self._build_metric_columns(report, options, "", monthly_values, figure_type),
            "level": 1,
        }

    def _build_metric_columns(self, report, options, metric_name, monthly_values, figure_type):
        columns = []
        for column in options["columns"]:
            expression_label = column["expression_label"]
            if expression_label == "metric_label":
                column_value = metric_name
                column_figure_type = "string"
            elif expression_label == "year_total":
                column_value = sum(monthly_values[month_index] for month_index in range(1, 13))
                column_figure_type = figure_type
            else:
                month_number = int(expression_label.split("_")[1])
                column_value = monthly_values[month_number]
                column_figure_type = figure_type

            columns.append(
                report._build_column_dict(
                    column_value,
                    {**column, "figure_type": column_figure_type},
                    options=options,
                    currency=self.env.company.currency_id if column_figure_type == "monetary" else False,
                    digits=2,
                )
            )
        return columns
