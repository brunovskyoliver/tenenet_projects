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


class TenenetCashflowReportHandler(models.AbstractModel):
    _name = "tenenet.cashflow.report.handler"
    _inherit = ["account.report.custom.handler"]
    _description = "TENENET CashFlow Report Handler"

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        custom_display_config = options["custom_display_config"]
        custom_display_config["css_custom_class"] = (
            custom_display_config.get("css_custom_class", "") + " tenenet_cashflow_report"
        ).strip()
        custom_display_config.setdefault("components", {})["AccountReportFilters"] = (
            "TenenetCashflowReportFilters"
        )
        self._set_year_options(options, self._get_selected_year(options))

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        selected_year = self._get_selected_year(options)
        editable_rows = self._get_effective_editable_rows(selected_year)
        self.env["tenenet.cashflow.global.override"].sync_year_rows(selected_year, editable_rows)

        income_rows = [row for row in editable_rows if row["row_type"] == "income"]
        salary_row = next(
            (row for row in editable_rows if row["row_type"] == "salary"),
            self._make_salary_row(defaultdict(float)),
        )
        project_expense_rows = [row for row in editable_rows if row["row_type"] == "expense"]
        cash_in_by_month = self._sum_rows_by_month(income_rows)
        cash_out_by_month = self._sum_rows_by_month([salary_row] + project_expense_rows)
        balance_by_month = defaultdict(float)

        for month in range(1, 13):
            balance_by_month[month] = cash_in_by_month[month] + cash_out_by_month[month]

        lines = []
        for index, income_row in enumerate(income_rows, 1):
            lines.append((0, self._build_report_line(
                report,
                options,
                income_row["program"],
                income_row["row_label"],
                income_row["values"],
                markup=f"cashflow_income_{index}",
                level=2,
            )))

        lines.append((0, self._build_report_line(
            report, options, "", "Cash-IN", cash_in_by_month, markup="cashflow_cash_in", level=1
        )))
        lines.append((0, self._build_spacer_line(report, options, "cashflow_spacer_after_cash_in")))
        lines.append((0, self._build_report_line(
            report,
            options,
            "",
            salary_row["row_label"],
            salary_row["values"],
            markup="cashflow_mzdy",
            level=1,
            is_expense=True,
        )))

        for index, expense_row in enumerate(project_expense_rows, 1):
            lines.append((0, self._build_report_line(
                report,
                options,
                expense_row["program"],
                expense_row["row_label"],
                expense_row["values"],
                markup=f"cashflow_project_expense_{index}",
                level=2,
                is_expense=True,
            )))

        lines.append((0, self._build_report_line(
            report, options, "", "Cash-OUT", cash_out_by_month, markup="cashflow_cash_out", level=1, is_expense=True
        )))
        lines.append((0, self._build_report_line(
            report,
            options,
            "",
            "Balance per actual month",
            balance_by_month,
            markup="cashflow_balance",
            level=1,
        )))
        return lines

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

    def _get_effective_editable_rows(self, selected_year):
        forecast_rows = self._get_forecast_editable_rows(selected_year)
        forecast_by_key = {row["row_key"]: row for row in forecast_rows}
        override_rows = self.env["tenenet.cashflow.global.override"].get_year_row_data(selected_year)
        effective_rows = []

        for row_key, forecast_row in forecast_by_key.items():
            override_row = override_rows.get(row_key)
            row = {
                **forecast_row,
                "values": defaultdict(float, forecast_row["values"]),
            }

            if override_row and row["row_type"] != "salary":
                for month, amount in override_row["values"].items():
                    row["values"][month] = amount

            if row["row_type"] == "salary" or any(row["values"].get(month, 0.0) for month in range(1, 13)):
                effective_rows.append(row)

        return sorted(
            effective_rows,
            key=lambda row: (row["sequence"], (row.get("program") or "").lower(), row["row_label"].lower()),
        )

    def _get_forecast_editable_rows(self, selected_year):
        income_rows = self._get_income_rows(selected_year)
        salary_row = self._make_salary_row(self._get_salary_by_month(selected_year))
        expense_rows = self._get_project_expense_rows(selected_year)
        rows = income_rows + [salary_row] + expense_rows
        return [
            row for row in rows
            if row["row_type"] == "salary" or any(row["values"].get(month, 0.0) for month in range(1, 13))
        ]

    def _get_income_rows(self, selected_year):
        rows = []
        project_values = {}

        cashflows = self.env["tenenet.project.cashflow"].search(
            [("receipt_year", "=", selected_year)],
            order="project_id, receipt_id, date_start",
        )
        for cashflow in cashflows:
            project = cashflow.project_id
            if project.id not in project_values:
                project_values[project.id] = {
                    "project": project,
                    "values": defaultdict(float),
                }
            project_values[project.id]["values"][cashflow.month] += cashflow.amount or 0.0

        for bucket in project_values.values():
            if not any(bucket["values"].values()):
                continue
            rows.append(self._make_income_row(bucket["project"], bucket["values"]))

        return sorted(rows, key=lambda row: ((row["program"] or "").lower(), row["row_label"].lower()))

    def _make_income_row(self, project, values):
        return {
            "row_key": f"income:{project.id}",
            "row_label": project.display_name,
            "row_type": "income",
            "section_label": "Príjmy",
            "program": self._get_program_label(project),
            "project_label": project.display_name,
            "sequence": 100,
            "values": defaultdict(float, values),
        }

    def _make_salary_row(self, values):
        return {
            "row_key": "salary:mzdy",
            "row_label": "Mzdy",
            "row_type": "salary",
            "section_label": "Výdavky",
            "program": "",
            "project_label": "Mzdy",
            "sequence": 200,
            "values": defaultdict(float, values),
        }

    def _get_salary_by_month(self, selected_year):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        result = defaultdict(float)

        timesheets = self.env["tenenet.project.timesheet"].with_context(active_test=False).search([
            ("period", ">=", year_start),
            ("period", "<=", year_end),
        ])
        for timesheet in timesheets:
            result[timesheet.period.month] -= timesheet.total_labor_cost or 0.0

        internal_expenses = self.env["tenenet.internal.expense"].sudo().search([
            ("period", ">=", year_start),
            ("period", "<=", year_end),
            ("category", "=", "leave"),
        ])
        for expense in internal_expenses:
            result[expense.period.month] -= expense.cost_ccp or 0.0

        return result

    def _get_project_expense_rows(self, selected_year):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        project_buckets = {}

        direct_expenses = self.env["tenenet.project.expense"].search([
            ("date", ">=", year_start),
            ("date", "<=", year_end),
        ])
        for expense in direct_expenses:
            bucket = project_buckets.setdefault(
                expense.project_id.id,
                {
                    "project": expense.project_id,
                    "values": defaultdict(float),
                },
            )
            bucket["values"][expense.date.month] -= expense.amount or 0.0

        internal_expenses = self.env["tenenet.internal.expense"].sudo().search([
            ("period", ">=", year_start),
            ("period", "<=", year_end),
            ("category", "=", "expense"),
        ])
        for expense in internal_expenses:
            project = expense.source_project_id or expense.source_assignment_id.project_id
            if not project:
                continue
            bucket = project_buckets.setdefault(
                project.id,
                {
                    "project": project,
                    "values": defaultdict(float),
                },
            )
            bucket["values"][expense.period.month] -= expense.expense_amount or 0.0

        rows = []
        for bucket in project_buckets.values():
            if not any(bucket["values"].values()):
                continue
            rows.append(self._make_project_expense_row(bucket["project"], bucket["values"]))

        return sorted(rows, key=lambda row: ((row["program"] or "").lower(), row["row_label"].lower()))

    def _make_project_expense_row(self, project, values):
        return {
            "row_key": f"expense:{project.id}",
            "row_label": f"Projektove naklady - {project.display_name}",
            "row_type": "expense",
            "section_label": "Výdavky",
            "program": self._get_program_label(project),
            "project_label": f"Projektove naklady - {project.display_name}",
            "sequence": 300,
            "values": defaultdict(float, values),
        }

    def _sum_rows_by_month(self, rows):
        result = defaultdict(float)
        for month in range(1, 13):
            result[month] = sum(row["values"].get(month, 0.0) for row in rows)
        return result

    def _get_program_label(self, project):
        return ", ".join(project.program_ids.mapped("name"))

    def _build_report_line(self, report, options, program_name, project_name, monthly_values, markup, level, is_expense=False):
        line = {
            "id": report._get_generic_line_id(None, None, markup=markup),
            "name": program_name or "",
            "columns": self._build_columns(report, options, project_name, monthly_values),
            "level": level,
        }
        if is_expense:
            line["class"] = "cashflow_expense_line"
        return line

    def _build_spacer_line(self, report, options, markup):
        columns = [
            report._build_column_dict(
                "",
                {**column, "figure_type": "string"},
                options=options,
            )
            for column in options["columns"]
        ]
        return {
            "id": report._get_generic_line_id(None, None, markup=markup),
            "name": "",
            "columns": columns,
            "level": 1,
            "class": "cashflow_spacer_line",
        }

    def _build_columns(self, report, options, project_name, monthly_values):
        columns = []
        for column in options["columns"]:
            expression_label = column["expression_label"]
            if expression_label == "project_label":
                value = project_name or ""
                figure_type = "string"
            elif expression_label == "year_total":
                value = sum(monthly_values.get(month, 0.0) for month in range(1, 13))
                figure_type = "monetary"
            else:
                month_number = int(expression_label.split("_")[1])
                value = monthly_values.get(month_number, 0.0)
                figure_type = "monetary"

            columns.append(
                report._build_column_dict(
                    value,
                    {**column, "figure_type": figure_type},
                    options=options,
                    currency=self.env.company.currency_id if figure_type == "monetary" else False,
                    digits=2,
                )
            )
        return columns
