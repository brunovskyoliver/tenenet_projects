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
        "Mzdy, stravné, CP a odvody - TNNT, odstupné, rekreačné, ročné zúčtovanie (máj)",
    ),
    ("kalia", "Mzdy, stravné, CP a odvody - Kalia"),
    ("scpp", "Mzdy, stravné, CP a odvody - SCPP"),
    ("wellnea", "Mzdy, stravné, CP a odvody - Wellnea, IDA tím"),
    ("pas_psc", "Mzdy, stravné, CP a odvody - nové PAS a PSC"),
]

WORKBOOK_EXPENSE_PREFIX_SEQUENCE = {
    "Stravne": 250,
    "Projektový náklad": 300,
    "Projektové náklady": 300,
    "Prevádzkové náklady": 350,
    "Investičné náklady": 400,
    "Finančné náklady": 450,
}

EXPENSE_MAPPING_TOKENS = [
    ("najom", "Prevádzkové náklady - nájom"),
    ("prenajom", "Prevádzkové náklady - nájom"),
    ("energie", "Prevádzkové náklady - energie"),
    ("tel", "Prevádzkové náklady - telekomunikácie a internet"),
    ("internet", "Prevádzkové náklady - telekomunikácie a internet"),
    ("it", "Prevádzkové náklady - IT služby a tlačiarne (DV)"),
    ("tlac", "Prevádzkové náklady - IT služby a tlačiarne (DV)"),
    ("prav", "Prevádzkové náklady - právne služby (CLS) a audit (JP)"),
    ("audit", "Prevádzkové náklady - právne služby (CLS) a audit (JP)"),
    ("hr", "Prevádzkové náklady - HR, vzdelávanie a supervízia"),
    ("vzdel", "Prevádzkové náklady - HR, vzdelávanie a supervízia"),
    ("market", "Prevádzkové náklady - marketing a PR"),
    ("pr", "Prevádzkové náklady - marketing a PR"),
    ("auto", "Prevádzkové náklady - poistenie a opravy, poistenie budov"),
    ("poisten", "Prevádzkové náklady - poistenie a opravy, poistenie budov"),
    ("staveb", "Prevádzkové náklady - stavebné práce a architekt"),
    ("architekt", "Prevádzkové náklady - stavebné práce a architekt"),
    ("vo", "Prevádzkové náklady - dane, poplatky a jednorazové položky"),
    ("dan", "Prevádzkové náklady - dane, poplatky a jednorazové položky"),
    ("kart", "Prevádzkové náklady - platby a výbery kartou"),
    ("ostat", "Prevádzkové náklady - ostatné všeobecné náklady"),
    ("cest", "Projektový náklad - Guide, Stem, MinM, EASY"),
    ("guide", "Projektový náklad - Guide, Stem, MinM, EASY"),
    ("stem", "Projektový náklad - Guide, Stem, MinM, EASY"),
    ("minm", "Projektový náklad - Guide, Stem, MinM, EASY"),
    ("easy", "Projektový náklad - Guide, Stem, MinM, EASY"),
    ("icm", "Projektové náklady - ICM"),
    ("pas", "Investičné náklady - PAS Prešov"),
    ("invest", "Investičné náklady - vybavenie"),
    ("uver", "Finančné náklady - úver SLSP, kontokorent, úrok, transakčná daň - W"),
    ("financ", "Finančné náklady - úver SLSP, kontokorent, úrok, transakčná daň - W"),
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
    _SALARY_GROUP_MARKUP = "cashflow_salary_group"
    _PROJECT_EXPENSE_GROUP_MARKUP = "cashflow_project_expenses_group"
    _OPERATING_EXPENSE_GROUP_MARKUP = "cashflow_operating_expenses_group"

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
        salary_total_row = next((row for row in salary_rows if row["row_key"] == "salary:mzdy"), None)
        salary_detail_rows = [row for row in salary_rows if row["row_key"] != "salary:mzdy"]
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
            report, options, "", "Príjmy", cash_in_by_month, markup="cashflow_cash_in", level=1
        )))
        lines.append((0, self._build_spacer_line(report, options, "cashflow_spacer_after_cash_in")))
        if salary_total_row:
            lines.append((0, self._build_group_line(
                report,
                options,
                "Mzdy",
                salary_total_row["values"],
                self._SALARY_GROUP_MARKUP,
                "_report_expand_unfoldable_line_cashflow_salary_group",
                level=1,
                unfoldable=bool(salary_detail_rows),
            )))

        grouped_project_expense_rows, grouped_operating_expense_rows, other_expense_rows = self._split_expense_rows(
            project_expense_rows
        )
        if grouped_project_expense_rows:
            lines.append((0, self._build_group_line(
                report,
                options,
                "Projektové náklady",
                self._sum_rows_by_month(grouped_project_expense_rows),
                self._PROJECT_EXPENSE_GROUP_MARKUP,
                "_report_expand_unfoldable_line_cashflow_project_expenses",
                level=1,
                unfoldable=True,
            )))
        if grouped_operating_expense_rows:
            lines.append((0, self._build_group_line(
                report,
                options,
                "Prevádzkové náklady",
                self._sum_rows_by_month(grouped_operating_expense_rows),
                self._OPERATING_EXPENSE_GROUP_MARKUP,
                "_report_expand_unfoldable_line_cashflow_operating_expenses",
                level=1,
                unfoldable=True,
            )))

        for index, expense_row in enumerate(other_expense_rows, 1):
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
            report, options, "", "Výdavky", cash_out_by_month, markup="cashflow_cash_out", level=1, is_expense=True
        )))
        lines.append((0, self._build_report_line(
            report,
            options,
            "",
            "Mesačný zostatok",
            balance_by_month,
            markup="cashflow_balance",
            level=1,
        )))
        return lines

    def _report_expand_unfoldable_line_cashflow_salary_group(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        selected_year = self._get_selected_year(options)
        editable_rows = self._get_effective_editable_rows(selected_year, options)
        rows = [row for row in editable_rows if row["row_type"] == "salary" and row["row_key"] != "salary:mzdy"]
        lines = []
        for index, salary_row in enumerate(rows, 1):
            lines.append(self._build_report_line(
                report,
                options,
                "Mzdy",
                salary_row["row_label"],
                salary_row["values"],
                markup=f"cashflow_salary_detail_{index}",
                level=2,
                is_expense=True,
                parent_line_id=line_dict_id,
            ))
        return self._build_expand_result(lines, progress)

    def _report_expand_unfoldable_line_cashflow_project_expenses(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        rows = self._get_grouped_expense_rows(options)[0]
        lines = []
        for index, expense_row in enumerate(rows, 1):
            program_name, project_name = self._split_cashflow_expense_label(expense_row["row_label"])
            lines.append(self._build_report_line(
                report,
                options,
                program_name,
                project_name,
                expense_row["values"],
                markup=f"cashflow_project_expense_detail_{index}",
                level=2,
                is_expense=True,
                parent_line_id=line_dict_id,
            ))
        return self._build_expand_result(lines, progress)

    def _report_expand_unfoldable_line_cashflow_operating_expenses(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        rows = self._get_grouped_expense_rows(options)[1]
        lines = []
        for index, expense_row in enumerate(rows, 1):
            program_name, project_name = self._split_cashflow_expense_label(expense_row["row_label"])
            lines.append(self._build_report_line(
                report,
                options,
                program_name,
                project_name,
                expense_row["values"],
                markup=f"cashflow_operating_expense_detail_{index}",
                level=2,
                is_expense=True,
                parent_line_id=line_dict_id,
            ))
        return self._build_expand_result(lines, progress)

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

        explicit_selected_ids = set(((options or {}).get("project_ids") or [])[:1])
        if explicit_selected_ids:
            effective_rows = [
                row for row in effective_rows
                if row["row_type"] != "expense" or row.get("project_id") in explicit_selected_ids
            ]

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
            mapped = self._get_expense_cashflow_mapping(expense.expense_type_config_id)
            project = expense.source_project_id or expense.source_assignment_id.project_id
            if not project and mapped:
                row_key, row_label = mapped
                bucket = row_buckets.setdefault(row_key, {
                    "row_label": row_label,
                    "values": defaultdict(float),
                })
                bucket["values"][expense.period.month] -= expense.expense_amount or 0.0
                continue
            if not project or project.id not in (selected_project_ids or []):
                continue
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
            fallback = config.cashflow_row_label or config.display_name
            return config.cashflow_row_key, self._label_from_cashflow_row_key(config.cashflow_row_key, fallback)
        key = _fold(f"{config.name or ''} {config.description or ''}")
        for token, label in EXPENSE_MAPPING_TOKENS:
            if token in key:
                return f"workbook:expense:{_slug(label)}", label
        other_config = self.env["tenenet.expense.type.config"].with_context(active_test=False).search(
            [("seed_key", "=", "operating_other")],
            limit=1,
        )
        if other_config and other_config.cashflow_row_key:
            fallback = other_config.cashflow_row_label or other_config.display_name
            return other_config.cashflow_row_key, self._label_from_cashflow_row_key(other_config.cashflow_row_key, fallback)
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
            "row_label": project.display_name,
            "row_type": "expense",
            "section_label": "Výdavky",
            "program": self._get_program_label(project),
            "project_label": project.display_name,
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

    def _split_expense_rows(self, expense_rows):
        project_rows = []
        operating_rows = []
        other_rows = []
        for row in expense_rows:
            label = row["row_label"]
            if row["row_key"].startswith("expense:") or self._is_project_expense_label(label):
                project_rows.append(row)
            elif self._is_operating_expense_label(label):
                operating_rows.append(row)
            else:
                other_rows.append(row)
        return project_rows, operating_rows, other_rows

    def _split_cashflow_expense_label(self, label):
        if label.startswith("Projektový náklad - "):
            return "Projektový náklad", label.removeprefix("Projektový náklad - ")
        if label.startswith("Projektové náklady - "):
            return "Projektové náklady", label.removeprefix("Projektové náklady - ")
        if label.startswith("Projektovy naklad - "):
            return "Projektový náklad", label.removeprefix("Projektovy naklad - ")
        if label.startswith("Projektove naklady - "):
            return "Projektové náklady", label.removeprefix("Projektove naklady - ")
        if label.startswith("Prevádzkové náklady - "):
            return "Prevádzkové náklady", label.removeprefix("Prevádzkové náklady - ")
        if label.startswith("Prevadzkove N - "):
            return "Prevádzkové náklady", label.removeprefix("Prevadzkove N - ")
        if label.startswith("Prevadzkova N - "):
            return "Prevádzkové náklady", label.removeprefix("Prevadzkova N - ")
        return "", label

    def _is_project_expense_label(self, label):
        return label.startswith(("Projektový náklad", "Projektové náklady", "Projektovy naklad", "Projektove naklady"))

    def _is_operating_expense_label(self, label):
        return label.startswith(("Prevádzkové náklady", "Prevadzkove N", "Prevadzkova N"))

    def _get_grouped_expense_rows(self, options):
        selected_year = self._get_selected_year(options)
        effective_rows = self._get_effective_editable_rows(selected_year, options)
        expense_rows = [row for row in effective_rows if row["row_type"] == "expense"]
        return self._split_expense_rows(expense_rows)

    def _get_program_label(self, project):
        if not project:
            return ""
        admin_program = project._get_admin_tenenet_program()
        program = project._get_primary_visible_program()
        if program:
            return program.display_name or program.name or ""
        if project.primary_program_id and project.primary_program_id != admin_program:
            return project.primary_program_id.display_name or project.primary_program_id.name or ""
        if project.reporting_program_id and project.reporting_program_id != admin_program:
            return project.reporting_program_id.display_name or project.reporting_program_id.name or ""
        fallback = project.program_ids.filtered(lambda rec: rec != admin_program)[:1] or project.program_ids[:1]
        return fallback.display_name or fallback.name or ""

    def _build_report_line(
        self,
        report,
        options,
        program_name,
        project_name,
        monthly_values,
        markup,
        level,
        is_expense=False,
        parent_line_id=None,
    ):
        line = {
            "id": report._get_generic_line_id(None, None, parent_line_id=parent_line_id, markup=markup),
            "name": program_name or "",
            "columns": self._build_columns(report, options, project_name, monthly_values),
            "level": level,
        }
        if parent_line_id:
            line["parent_id"] = parent_line_id
        if is_expense:
            line["class"] = "cashflow_expense_line"
        return line

    def _build_group_line(
        self, report, options, group_name, monthly_values, markup, expand_function, level, unfoldable=True
    ):
        line = self._build_report_line(
            report,
            options,
            group_name,
            "",
            monthly_values,
            markup=markup,
            level=level,
            is_expense=True,
        )
        line["unfoldable"] = unfoldable
        line["unfolded"] = bool(
            unfoldable
            and (
                options.get("unfold_all")
                or line["id"] in (options.get("unfolded_lines") or [])
            )
        )
        line["expand_function"] = expand_function if unfoldable else None
        return line

    def _build_expand_result(self, lines, progress):
        return {
            "lines": lines,
            "offset_increment": len(lines),
            "has_more": False,
            "progress": progress,
        }

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
