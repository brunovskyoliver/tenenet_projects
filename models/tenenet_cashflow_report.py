from collections import defaultdict
from datetime import date
import re
import unicodedata

from odoo import models


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

SALARY_ROW_SPECS = [
    (
        "tnnt",
        "Mzdy, stravne,CP a odvody - TNNT, odstupne, rekreacne, rocne zuctovanie (maj)",
    ),
    ("kalia", "Mzdy, stravne, CP a odvody - Kalia"),
    ("scpp", "Mzdy, stravne, CP a odvody - SCPP"),
    ("wellnea", "Mzdy, stravne, CP a odvody - Wellnea, IDA tim"),
    ("pas_psc", "Mzdy stravne, CP a odvody - nove PAS a PSC"),
]

WORKBOOK_EXPENSE_PREFIX_SEQUENCE = {
    "Stravne": 250,
    "Projektovy naklad": 300,
    "Projektove naklady": 300,
    "Prevadzkove N": 350,
    "Prevadzkova N": 350,
    "Investicne N": 400,
    "Financny N": 450,
}

EXPENSE_MAPPING_TOKENS = [
    ("najom", "Prevadzkove N - najom"),
    ("prenajom", "Prevadzkove N - najom"),
    ("energie", "Prevadzkove N - energie"),
    ("tel", "Prevadzkove N - Tel a internet"),
    ("internet", "Prevadzkove N - Tel a internet"),
    ("it", "Prevadzkove N - IT slu & tlaciarne (DV)"),
    ("tlac", "Prevadzkove N - IT slu & tlaciarne (DV)"),
    ("prav", "Prevadzkove N - Pravne sluzby (CLS), audit (JP)"),
    ("audit", "Prevadzkove N - Pravne sluzby (CLS), audit (JP)"),
    ("hr", "Prevadzkova N - HR costs - vzdelavanie (superv. a SK)"),
    ("vzdel", "Prevadzkova N - HR costs - vzdelavanie (superv. a SK)"),
    ("market", "Prevadzkova N - Market, PR costs (TT)"),
    ("pr", "Prevadzkova N - Market, PR costs (TT)"),
    ("auto", "Prevadzkove N - Auta (poistenie, opravy), poistenie budov"),
    ("poisten", "Prevadzkove N - Auta (poistenie, opravy), poistenie budov"),
    ("staveb", "Prevadzkove N - Stavebne, architekt"),
    ("architekt", "Prevadzkove N - Stavebne, architekt"),
    ("vo", "Prevadzkove N - One-off items, VO, dane"),
    ("dan", "Prevadzkove N - One-off items, VO, dane"),
    ("kart", "Prevadzkove N - Platby kartou, vyber kartou"),
    ("ostat", "Prevadzkove N - Other general costs (n/m)"),
    ("cest", "Projektovy naklad -Guide, Stem, MinM, EASY"),
    ("guide", "Projektovy naklad -Guide, Stem, MinM, EASY"),
    ("stem", "Projektovy naklad -Guide, Stem, MinM, EASY"),
    ("minm", "Projektovy naklad -Guide, Stem, MinM, EASY"),
    ("easy", "Projektovy naklad -Guide, Stem, MinM, EASY"),
    ("icm", "Projektove naklady - ICM"),
    ("pas", "Investicne N - PAS Presov"),
    ("invest", "Investicne N - vybavenie"),
    ("uver", "Financny N - Uver SLSP, kontokorent urok, transakcna dan - W"),
    ("financ", "Financny N - Uver SLSP, kontokorent urok, transakcna dan - W"),
]


def _fold(value):
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def _slug(value):
    text = re.sub(r"[^a-z0-9]+", "-", _fold(value))
    return text.strip("-") or "row"


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
        salary_rows = [row for row in editable_rows if row["row_type"] == "salary"]
        project_expense_rows = [row for row in editable_rows if row["row_type"] == "expense"]
        cash_out_salary_rows = [row for row in salary_rows if row["row_key"] != "salary:mzdy"] or salary_rows
        cash_in_by_month = self._sum_rows_by_month(income_rows)
        cash_out_by_month = self._sum_rows_by_month(cash_out_salary_rows + project_expense_rows)
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
        for index, salary_row in enumerate(salary_rows, 1):
            lines.append((0, self._build_report_line(
                report,
                options,
                salary_row["program"],
                salary_row["row_label"],
                salary_row["values"],
                markup=f"cashflow_salary_{index}",
                level=1 if salary_row["row_key"] == "salary:mzdy" else 2,
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

    def _get_effective_editable_rows(self, selected_year, options=None):
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

            if override_row and row.get("source_kind") == "workbook_actual":
                plan_values = defaultdict(float, override_row["values"])
                for month, amount in row["values"].items():
                    if amount:
                        plan_values[month] = amount
                row["values"] = plan_values
            elif override_row and row["row_type"] != "salary":
                for month, amount in override_row["values"].items():
                    row["values"][month] = amount

            if row["row_type"] == "salary" or any(row["values"].get(month, 0.0) for month in range(1, 13)):
                effective_rows.append(row)

        for row_key, override_row in override_rows.items():
            if row_key in forecast_by_key:
                continue
            if override_row["row_type"] == "salary" or any(override_row["values"].get(month, 0.0) for month in range(1, 13)):
                effective_rows.append({
                    **override_row,
                    "values": defaultdict(float, override_row["values"]),
                })

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
        salary_values = self._get_salary_by_month(selected_year, selected_project_ids)
        salary_row = self._make_salary_row(self._sum_salary_buckets(salary_values))
        salary_rows = [salary_row]
        for group_key, label in SALARY_ROW_SPECS:
            values = salary_values.get(group_key, defaultdict(float))
            if any(values.values()):
                salary_rows.append(self._make_salary_group_row(group_key, label, values))
        expense_rows = self._get_project_expense_rows(selected_year, options)
        rows = income_rows + salary_rows + expense_rows
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

    def _make_salary_group_row(self, group_key, label, values):
        return {
            "row_key": f"workbook:salary:{_slug(label)}",
            "row_label": label,
            "row_type": "salary",
            "section_label": "Výdavky",
            "program": "",
            "project_label": label,
            "sequence": 210,
            "source_kind": "workbook_actual",
            "actual_mapping_key": f"salary:{group_key}",
            "values": defaultdict(float, values),
        }

    def _get_salary_by_month(self, selected_year, selected_project_ids):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        result = {key: defaultdict(float) for key, _label in SALARY_ROW_SPECS}

        timesheets = self.env["tenenet.project.timesheet"].with_context(active_test=False).search([
            ("period", ">=", year_start),
            ("period", "<=", year_end),
            ("project_id", "in", selected_project_ids or [0]),
        ])
        for timesheet in timesheets:
            group_key = self._get_salary_group_key(timesheet.project_id)
            result[group_key][timesheet.period.month] -= timesheet.total_labor_cost or 0.0

        internal_expenses = self.env["tenenet.internal.expense"].sudo().search([
            ("period", ">=", year_start),
            ("period", "<=", year_end),
            ("category", "in", ["leave", "residual_wage"]),
        ])
        for expense in internal_expenses:
            project = expense.source_project_id or (expense.source_assignment_id.project_id if expense.source_assignment_id else False)
            if not project or project.id not in (selected_project_ids or []):
                continue
            group_key = self._get_salary_group_key(project)
            result[group_key][expense.period.month] -= expense.cost_ccp or 0.0

        return result

    def _sum_salary_buckets(self, buckets):
        result = defaultdict(float)
        for values in buckets.values():
            for month, amount in values.items():
                result[month] += amount
        return result

    def _get_salary_group_key(self, project):
        name_key = _fold(project.display_name or "")
        program_codes = set(project.program_ids.mapped("code"))
        org_code = project.organizational_unit_id.code if project.organizational_unit_id else ""
        if org_code == "KALIA":
            return "kalia"
        if org_code == "SCPP":
            return "scpp"
        if org_code == "WELLNEA":
            return "wellnea"
        if "PSC" in name_key.upper() or any((code or "").startswith("PSC") for code in program_codes):
            return "pas_psc"
        if "pas" in name_key:
            return "pas_psc"
        return "tnnt"

    def _get_project_expense_rows(self, selected_year, options):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        selected_project_ids = self._get_selected_project_ids_from_options(options)
        row_buckets = {}
        project_buckets = {}

        direct_expenses = self.env["tenenet.project.expense"].search([
            ("date", ">=", year_start),
            ("date", "<=", year_end),
            ("project_id", "in", selected_project_ids or [0]),
        ])
        for expense in direct_expenses:
            mapped = self._get_expense_cashflow_mapping(expense.expense_type_config_id)
            if mapped:
                row_key, row_label = mapped
                bucket = row_buckets.setdefault(row_key, {
                    "row_label": row_label,
                    "values": defaultdict(float),
                })
                bucket["values"][expense.date.month] -= expense.amount or 0.0
                continue
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
            mapped = self._get_expense_cashflow_mapping(expense.expense_type_config_id)
            if mapped:
                row_key, row_label = mapped
                bucket = row_buckets.setdefault(row_key, {
                    "row_label": row_label,
                    "values": defaultdict(float),
                })
                bucket["values"][expense.period.month] -= expense.expense_amount or 0.0
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
        for row_key, bucket in row_buckets.items():
            if any(bucket["values"].values()):
                rows.append(self._make_mapped_expense_row(row_key, bucket["row_label"], bucket["values"]))
        for bucket in project_buckets.values():
            if not any(bucket["values"].values()):
                continue
            rows.append(self._make_project_expense_row(bucket["project"], bucket["values"]))

        return sorted(rows, key=lambda row: ((row["program"] or "").lower(), row["row_label"].lower()))

    def _get_expense_cashflow_mapping(self, config):
        if not config:
            return False
        if config.cashflow_row_key:
            return config.cashflow_row_key, self._label_from_cashflow_row_key(config.cashflow_row_key, config.display_name)
        key = _fold(f"{config.name or ''} {config.description or ''}")
        for token, label in EXPENSE_MAPPING_TOKENS:
            if token in key:
                return f"workbook:expense:{_slug(label)}", label
        return False

    def _label_from_cashflow_row_key(self, row_key, fallback):
        Override = self.env["tenenet.cashflow.global.override"].sudo()
        row = Override.search([("row_key", "=", row_key)], limit=1)
        return row.row_label if row else (fallback or row_key)

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

    def _make_mapped_expense_row(self, row_key, row_label, values):
        return {
            "row_key": row_key,
            "row_label": row_label,
            "row_type": "expense",
            "section_label": "Výdavky",
            "program": "",
            "project_label": row_label,
            "sequence": self._expense_sequence(row_label),
            "source_kind": "workbook_actual",
            "actual_mapping_key": row_key,
            "values": defaultdict(float, values),
        }

    def _expense_sequence(self, row_label):
        for prefix, sequence in WORKBOOK_EXPENSE_PREFIX_SEQUENCE.items():
            if row_label.startswith(prefix):
                return sequence
        return 300

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
