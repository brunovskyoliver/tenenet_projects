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
    _inherit = ["account.report.custom.handler", "tenenet.pl.reporting.support"]
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
        available_projects = self.env["tenenet.project"].get_report_accessible_projects()
        options["available_project_domain"] = [("id", "in", available_projects.ids or [0])]
        selected_project = self._get_selected_project(previous_options, available_projects=available_projects)
        options["project_ids"] = [selected_project.id] if selected_project else []
        options["selected_project_name"] = selected_project.display_name if selected_project else "Všetky projekty"
        self._set_year_options(options, self._get_selected_year(options))

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        selected_year = self._get_selected_year(options)
        editable_rows = self._get_effective_editable_rows(selected_year, options)
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

    def _get_effective_editable_rows(self, selected_year, options):
        forecast_rows = self._get_forecast_editable_rows(selected_year, options)
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

    def _get_forecast_editable_rows(self, selected_year, options):
        selected_project_ids = self._get_selected_project_ids_from_options(options)
        income_rows = [
            row for row in self._get_income_rows(selected_year)
            if row.get("project_id") in set(selected_project_ids or [])
        ]
        salary_row = self._make_salary_row(self._get_salary_by_month(selected_year, selected_project_ids))
        expense_rows = self._get_project_expense_rows(selected_year, options)
        rows = income_rows + [salary_row] + expense_rows
        return [
            row for row in rows
            if row["row_type"] == "salary" or any(row["values"].get(month, 0.0) for month in range(1, 13))
        ]

    def _get_income_rows(self, selected_year):
        return super()._get_income_rows(selected_year)

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

    def _get_salary_by_month(self, selected_year, selected_project_ids):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        result = defaultdict(float)

        timesheets = self.env["tenenet.project.timesheet"].with_context(active_test=False).search([
            ("period", ">=", year_start),
            ("period", "<=", year_end),
            ("project_id", "in", selected_project_ids or [0]),
        ])
        for timesheet in timesheets:
            result[timesheet.period.month] -= timesheet.total_labor_cost or 0.0

        internal_expenses = self.env["tenenet.internal.expense"].sudo().search([
            ("period", ">=", year_start),
            ("period", "<=", year_end),
            ("category", "in", ["leave", "residual_wage"]),
        ])
        for expense in internal_expenses:
            project = expense.source_project_id or (expense.source_assignment_id.project_id if expense.source_assignment_id else False)
            if not project or project.id not in (selected_project_ids or []):
                continue
            result[expense.period.month] -= expense.cost_ccp or 0.0

        return result

    def _get_project_expense_rows(self, selected_year, options):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        selected_project_ids = self._get_selected_project_ids_from_options(options)
        project_buckets = {}

        direct_expenses = self.env["tenenet.project.expense"].search([
            ("date", ">=", year_start),
            ("date", "<=", year_end),
            ("project_id", "in", selected_project_ids or [0]),
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
            if not project or project.id not in (selected_project_ids or []):
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

    def _get_selected_project(self, options, available_projects=None):
        allowed_projects = available_projects or self.env["tenenet.project"].get_report_accessible_projects()
        project_ids = (options or {}).get("project_ids") or []
        project_id = project_ids[:1]
        if project_id:
            project = self.env["tenenet.project"].with_context(active_test=False).browse(project_id[0]).exists()
            if project and project in allowed_projects:
                return project
        return False

    def _get_selected_project_ids_from_options(self, options):
        selected_ids = ((options or {}).get("project_ids") or [])[:1]
        if selected_ids:
            return selected_ids
        return self.env["tenenet.project"].get_report_accessible_project_ids()

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
