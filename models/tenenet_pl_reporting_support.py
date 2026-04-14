from collections import defaultdict
from datetime import date

from odoo import fields, models


class TenenetPLReportingSupport(models.AbstractModel):
    _name = "tenenet.pl.reporting.support"
    _description = "TENENET P&L Reporting Support"
    _BUDGET_INCOME_SECTION_METADATA = {
        "labor": {
            "label": "Mzdové rozpočty",
            "markup": "tenenet_pl_budget_income_labor",
        },
        "other": {
            "label": "Iné rozpočty",
            "markup": "tenenet_pl_budget_income_other",
        },
    }

    _ROW_SPEC_METADATA = {
        "sales_individual": {
            "row_label": "Tržby individuálne",
            "sequence": 305,
            "section_label": "Príjmy",
            "is_editable": False,
        },
        "sales_cash_register": {
            "row_label": "Tržby z registračky",
            "sequence": 300,
            "section_label": "Príjmy",
            "is_editable": True,
        },
        "sales_invoice": {
            "row_label": "Tržby z faktúr",
            "sequence": 310,
            "section_label": "Príjmy",
            "is_editable": True,
        },
        "sales_legacy_unclassified": {
            "row_label": "Tržby - neklasifikované",
            "sequence": 320,
            "section_label": "Príjmy",
            "is_editable": True,
        },
        "operating_income": {
            "row_label": "Prevádzkové príjmy",
            "sequence": 345,
            "section_label": "Príjmy",
            "is_editable": True,
        },
        "stravne": {
            "row_label": "Stravné a iné",
            "sequence": 520,
            "section_label": "Náklady",
            "is_editable": True,
        },
        "admin_tenenet_cost": {
            "row_label": "Admin TENENET náklady",
            "sequence": 800,
            "section_label": "Náklady",
            "is_editable": True,
        },
        "projects_total": {
            "row_label": "Projekty",
            "sequence": 100,
            "section_label": "Príjmy",
            "is_editable": False,
        },
        "sales_total": {
            "row_label": "Tržby",
            "sequence": 330,
            "section_label": "Príjmy",
            "is_editable": False,
        },
        "fundraising_total": {
            "row_label": "Zbierky",
            "sequence": 340,
            "section_label": "Príjmy",
            "is_editable": False,
        },
        "fundraising_individual": {
            "row_label": "Zbierky individuálne",
            "sequence": 341,
            "section_label": "Príjmy",
            "is_editable": False,
        },
        "fundraising_corporate": {
            "row_label": "Zbierky korporátne",
            "sequence": 342,
            "section_label": "Príjmy",
            "is_editable": False,
        },
        "income_total": {
            "row_label": "Príjmy spolu",
            "sequence": 350,
            "section_label": "Príjmy",
            "is_editable": False,
        },
        "labor_cost": {
            "row_label": "Mzdové náklady - program",
            "sequence": 400,
            "section_label": "Náklady",
            "is_editable": False,
        },
        "labor_non_project": {
            "row_label": "Náklady bez projektov",
            "sequence": 430,
            "section_label": "Náklady",
            "is_editable": False,
        },
        "labor_mgmt": {
            "row_label": "Mzdové náklady administratívy",
            "sequence": 450,
            "section_label": "Náklady",
            "is_editable": True,
        },
        "labor_coverage": {
            "row_label": "Pokrytie mzdových nákladov",
            "sequence": 540,
            "section_label": "Náklady",
            "is_editable": False,
        },
        "pre_admin_result": {
            "row_label": "Výsledok po mzdových nákladoch",
            "sequence": 600,
            "section_label": "Náklady",
            "is_editable": False,
        },
        "operating": {
            "row_label": "Prevádzkové náklady",
            "sequence": 900,
            "section_label": "Náklady",
            "is_editable": False,
        },
        "final_result": {
            "row_label": "Výsledok programu",
            "sequence": 1000,
            "section_label": "Náklady",
            "is_editable": False,
        },
    }

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

    def _get_report_programs(self):
        return self.env["tenenet.program"].with_context(active_test=False).search([], order="name")

    def _get_default_program(self):
        return self._get_report_programs()[:1]

    def _get_selected_program_from_options(self, options):
        program_ids = (options or {}).get("program_ids") or []
        if program_ids:
            return self.env["tenenet.program"].with_context(active_test=False).browse(program_ids[0]).exists()
        return self._get_default_program()

    def _get_program_line_name(self, program):
        return program.display_name or program.name or ""

    def _get_project_line_name(self, project):
        code = (project.code or "").strip() if "code" in project._fields else ""
        name = (project.name or "").strip() or project.display_name or ""
        return f"{code} {name}".strip() if code else name

    def _get_program_label(self, project):
        if getattr(project, "reporting_program_id", False):
            return project.reporting_program_id.display_name or project.reporting_program_id.name or ""
        return ", ".join(project.program_ids.mapped("name"))

    def _get_admin_tenenet_program(self):
        return self.env["tenenet.program"].with_context(active_test=False).search(
            [("code", "=", "ADMIN_TENENET")],
            limit=1,
        )

    def _is_admin_tenenet_program(self, program):
        return bool(program and program.code == "ADMIN_TENENET")

    def _zero_by_month(self):
        return defaultdict(float, {month: 0.0 for month in range(1, 13)})

    def _is_value_bundle(self, values):
        return isinstance(values, dict) and {
            "values",
            "real_values",
            "predicted_values",
            "predicted_months",
            "has_prediction",
        }.issubset(values.keys())

    def _month_map_from_values(self, values):
        if self._is_value_bundle(values):
            values = values.get("values")
        return values or {}

    def _prediction_month_map(self, predicted_months=None):
        return {month: bool((predicted_months or {}).get(month)) for month in range(1, 13)}

    def _make_value_bundle(self, values=None, real_values=None, predicted_values=None, predicted_months=None):
        merged_values = self._copy_month_values(values)
        real_months = self._copy_month_values(real_values)
        predicted_months_values = self._copy_month_values(predicted_values)
        flags = self._prediction_month_map(predicted_months)
        if not values:
            merged_values = self._sum_month_dicts(real_months, predicted_months_values)
        return {
            "values": merged_values,
            "real_values": real_months,
            "predicted_values": predicted_months_values,
            "predicted_months": flags,
            "has_prediction": any(flags.values()),
        }

    def _value_bundle(self, values=None):
        if self._is_value_bundle(values):
            return self._make_value_bundle(
                values=values.get("values"),
                real_values=values.get("real_values"),
                predicted_values=values.get("predicted_values"),
                predicted_months=values.get("predicted_months"),
            )
        merged_values = self._copy_month_values(values)
        return self._make_value_bundle(values=merged_values, real_values=merged_values)

    def _sum_month_dicts(self, *value_maps):
        result = defaultdict(float)
        for month in range(1, 13):
            result[month] = sum(self._month_map_from_values(values).get(month, 0.0) for values in value_maps)
        return result

    def _copy_month_values(self, value_map=None):
        values = defaultdict(float)
        month_map = self._month_map_from_values(value_map)
        for month in range(1, 13):
            values[month] = month_map.get(month, 0.0)
        return values

    def _sum_month_value_bundles(self, *value_bundles):
        real_values = defaultdict(float)
        predicted_values = defaultdict(float)
        predicted_months = {}
        for month in range(1, 13):
            real_values[month] = sum(
                self._value_bundle(bundle)["real_values"].get(month, 0.0)
                for bundle in value_bundles
            )
            predicted_values[month] = sum(
                self._value_bundle(bundle)["predicted_values"].get(month, 0.0)
                for bundle in value_bundles
            )
            predicted_months[month] = any(
                self._value_bundle(bundle)["predicted_months"].get(month, False)
                for bundle in value_bundles
            )
        return self._make_value_bundle(
            real_values=real_values,
            predicted_values=predicted_values,
            predicted_months=predicted_months,
        )

    def _override_month_values(self, base_values, override_row):
        values = self._copy_month_values(base_values)
        if not override_row:
            return values
        manual_months = override_row.get("manual_months") or {}
        for month in range(1, 13):
            if manual_months.get(month):
                values[month] = (override_row.get("values") or {}).get(month, 0.0)
        return values

    def _predict_row_bundle(self, base_values, selected_year, override_row=None, annual_budget=None):
        values = self._override_month_values(base_values, override_row)
        today = fields.Date.context_today(self)
        if selected_year != today.year:
            if annual_budget is not None and not any(abs(values.get(month, 0.0)) > 0.00001 for month in range(1, 13)):
                monthly_amount = annual_budget / 12.0
                for month in range(1, 13):
                    values[month] = monthly_amount
            return self._make_value_bundle(values=values, real_values=values)

        past_months = range(1, today.month)
        future_months = range(today.month, 13)
        history = [values[month] for month in past_months if abs(values[month]) > 0.00001]
        predicted_value = sum(history) / len(history) if len(history) >= 2 else None
        manual_months = (override_row or {}).get("manual_months") or {}
        real_values = self._zero_by_month()
        predicted_values = self._zero_by_month()
        predicted_flags = {}

        for month in range(1, 13):
            if month < today.month:
                real_values[month] = values.get(month, 0.0)
                predicted_flags[month] = False
                continue

            month_value = values.get(month, 0.0)
            if manual_months.get(month) or abs(month_value) > 0.00001:
                predicted_values[month] = month_value
                predicted_flags[month] = abs(month_value) > 0.00001
                continue

            if predicted_value is not None:
                predicted_values[month] = predicted_value
                predicted_flags[month] = True
            else:
                predicted_flags[month] = False

        return self._make_value_bundle(
            real_values=real_values,
            predicted_values=predicted_values,
            predicted_months=predicted_flags,
        )

    def _predict_row_values(self, base_values, selected_year, override_row=None, annual_budget=None):
        return self._predict_row_bundle(
            base_values,
            selected_year,
            override_row=override_row,
            annual_budget=annual_budget,
        )["values"]

    def _predict_report_rows(self, rows, selected_year, override_resolver=None, nested_keys=None):
        nested_keys = tuple(nested_keys or ())
        predicted_rows = []
        for row in rows:
            row_copy = dict(row)
            override_row = override_resolver(row_copy) if override_resolver else None
            value_bundle = self._predict_row_bundle(
                row_copy.get("values"),
                selected_year,
                override_row=override_row,
            )
            row_copy["value_bundle"] = value_bundle
            row_copy["values"] = value_bundle["values"]
            for nested_key in nested_keys:
                if row_copy.get(nested_key):
                    row_copy[nested_key] = self._predict_report_rows(
                        row_copy[nested_key],
                        selected_year,
                    )
            predicted_rows.append(row_copy)
        return predicted_rows

    def _cashflow_override_rows(self, selected_year):
        return self.env["tenenet.cashflow.global.override"].get_year_row_data(selected_year)

    def _program_override_rows(self, selected_year, program):
        return self.env["tenenet.pl.program.override"].get_year_row_data(selected_year).get(program.id, {})

    def _has_nonzero_month_values(self, value_map):
        values = self._month_map_from_values(value_map)
        return any(abs(values.get(month, 0.0)) > 0.00001 for month in range(1, 13))

    def _get_non_admin_project_income_rows(self, program, selected_year, override_rows=None):
        budget_rows = []
        for budget_type in self._BUDGET_INCOME_SECTION_METADATA:
            budget_rows.extend(self._get_budget_income_rows(program, selected_year, budget_type))
        budget_rows = [row for row in budget_rows if not row["budget_line"].service_income_type]

        detail_rows_by_project = defaultdict(list)
        for row in budget_rows:
            project = row["project"]
            line = row["budget_line"]
            if line.name:
                row_name = line.name
            elif line.budget_type == "other" and line.expense_type_config_id:
                row_name = line.expense_type_config_id.display_name
            else:
                section_metadata = self._BUDGET_INCOME_SECTION_METADATA.get(row["budget_line"].budget_type, {})
                row_name = section_metadata.get("label") or row["name"]
            row_bundle = row.get("value_bundle") or self._value_bundle(row["values"])
            detail_rows_by_project[project.id].append({
                "name": row_name,
                "budget_line": line,
                "values": self._copy_month_values(row_bundle["values"]),
                "value_bundle": self._value_bundle(row_bundle),
            })

        project_ids = set(detail_rows_by_project)
        for row_key in (override_rows or {}):
            if not row_key.startswith("income:"):
                continue
            try:
                project_ids.add(int(row_key.split(":", 1)[1]))
            except (TypeError, ValueError):
                continue

        rows = []
        for project in self.env["tenenet.project"].with_context(active_test=False).browse(sorted(project_ids)).exists():
            if project.reporting_program_id != program:
                continue
            detail_rows = [
                {
                    **detail_row,
                    "values": self._copy_month_values(detail_row["values"]),
                    "value_bundle": self._value_bundle(detail_row["value_bundle"]),
                }
                for detail_row in detail_rows_by_project.get(project.id, [])
                if self._has_nonzero_month_values(detail_row["values"])
            ]
            detail_rows.sort(key=lambda row: (row["name"] or "").lower())
            project_bundle = self._sum_month_value_bundles(*(detail_row["value_bundle"] for detail_row in detail_rows))
            rows.append({
                "project": project,
                "name": self._get_project_line_name(project),
                "values": project_bundle["values"],
                "value_bundle": project_bundle,
                "detail_rows": detail_rows,
            })

        rows.sort(key=lambda row: (row["name"] or "").lower())
        return rows

    def _get_project_income_rows(self, program, selected_year, override_rows=None):
        if not self._is_admin_tenenet_program(program):
            return self._get_non_admin_project_income_rows(program, selected_year, override_rows=override_rows)

        project_values = {}
        cashflow_rows = self._cashflow_override_rows(selected_year)
        program_override_rows = self._program_override_rows(selected_year, program)
        receipts = self.env["tenenet.project.receipt"].search(
            [("year", "=", selected_year)],
            order="project_id, date_received, id",
        )
        for receipt in receipts:
            project = receipt.project_id
            if project.reporting_program_id != program:
                continue
            bucket = project_values.setdefault(
                project.id,
                {
                    "project": project,
                    "name": self._get_project_line_name(project),
                    "values": defaultdict(float),
                },
            )
            receipt_values = self._get_receipt_month_values(receipt)
            for month, amount in receipt_values.items():
                bucket["values"][month] += amount

        cashflows = self.env["tenenet.project.cashflow"].search(
            [("receipt_year", "=", selected_year)],
            order="project_id, receipt_id, date_start",
        )
        replaced_receipt_ids = set()
        for cashflow in cashflows:
            project = cashflow.project_id
            if project.reporting_program_id != program:
                continue
            bucket = project_values.setdefault(
                project.id,
                {
                    "project": project,
                    "name": self._get_project_line_name(project),
                    "values": defaultdict(float),
                },
            )
            if cashflow.receipt_id.id not in replaced_receipt_ids and (receipt_values := self._get_receipt_month_values(cashflow.receipt_id)):
                for month in receipt_values:
                    bucket["values"][month] -= receipt_values[month]
                replaced_receipt_ids.add(cashflow.receipt_id.id)
            bucket["values"][cashflow.month] += cashflow.amount or 0.0

        project_ids = set(project_values)
        project_ids.update(
            self.env["tenenet.project"].with_context(active_test=False).search([
                ("reporting_program_id", "=", program.id),
            ]).ids
        )
        for row_key in set(cashflow_rows) | set(program_override_rows):
            if not row_key.startswith("income:"):
                continue
            try:
                project_id = int(row_key.split(":", 1)[1])
            except (TypeError, ValueError):
                continue
            project = self.env["tenenet.project"].with_context(active_test=False).browse(project_id).exists()
            if project and project.reporting_program_id == program:
                project_ids.add(project_id)

        rows = []
        for project in self.env["tenenet.project"].with_context(active_test=False).browse(sorted(project_ids)).exists():
            bucket = project_values.get(
                project.id,
                {
                    "project": project,
                    "name": self._get_project_line_name(project),
                    "values": self._zero_by_month(),
                },
            )
            program_override_row = program_override_rows.get(f"income:{project.id}")
            override_row = cashflow_rows.get(f"income:{project.id}")
            values = self._copy_month_values(bucket["values"])
            if override_row:
                values = defaultdict(float, override_row.get("values") or {})
            values = self._override_month_values(values, program_override_row)
            if any(values.values()):
                rows.append({
                    **bucket,
                    "values": values,
                    "value_bundle": self._value_bundle(values),
                    "detail_rows": [],
                })

        if self._is_admin_tenenet_program(program):
            rows.extend(self._get_admin_pausal_income_rows(program, selected_year))

        rows.sort(key=lambda row: (row["name"] or "").lower())
        return self._merge_project_income_rows(rows)

    def _merge_project_income_rows(self, rows):
        merged = {}
        ordered_rows = []
        for row in rows:
            key = row["project"].id
            existing = merged.get(key)
            if existing:
                existing["values"] = self._sum_month_dicts(existing["values"], row["values"])
                existing.setdefault("detail_rows", []).extend(row.get("detail_rows") or [])
                continue
            copy_row = dict(row)
            copy_row["detail_rows"] = list(row.get("detail_rows") or [])
            merged[key] = copy_row
            ordered_rows.append(copy_row)
        return ordered_rows

    def _get_admin_pausal_income_rows(self, program, selected_year):
        if not self._is_admin_tenenet_program(program):
            return []
        budget_lines = self.env["tenenet.project.budget.line"].search(
            [
                ("year", "=", selected_year),
                ("budget_type", "=", "pausal"),
                ("project_id.is_tenenet_internal", "=", False),
                ("amount", "!=", 0.0),
            ],
            order="project_id, sequence, id",
        )
        rows = {}
        for line in budget_lines:
            project = line.project_id
            line_values = defaultdict(float, line._get_effective_month_amounts())
            bucket = rows.setdefault(
                project.id,
                {
                    "project": project,
                    "name": self._get_project_line_name(project),
                    "values": defaultdict(float),
                    "detail_rows": [],
                },
            )
            bucket["values"] = self._sum_month_dicts(bucket["values"], line_values)
            bucket["detail_rows"].append({
                "budget_line": line,
                "name": line.name,
                "values": line_values,
                "value_bundle": self._value_bundle(line_values),
            })
        result = list(rows.values())
        result.sort(key=lambda row: (row["name"] or "").lower())
        return result

    def _get_budget_income_detail_label(self, line):
        return f"{self._get_project_line_name(line.project_id)} / {line._get_detail_label()}".strip(" /")

    def _get_service_income_budget_rows(self, program, selected_year):
        budget_lines = self.env["tenenet.project.budget.line"].search(
            [
                ("year", "=", selected_year),
                ("budget_type", "=", "other"),
                ("program_id", "=", program.id),
                ("service_income_type", "!=", False),
                ("amount", "!=", 0.0),
            ],
            order="project_id, sequence, id",
        )
        rows = []
        for line in budget_lines:
            values = defaultdict(float, line._get_effective_month_amounts())
            rows.append({
                "budget_line": line,
                "project": line.project_id,
                "row_key": line.service_income_type,
                "name": line._get_detail_label(),
                "values": values,
                "value_bundle": self._value_bundle(values),
                "can_cover_payroll": bool(line.can_cover_payroll),
            })
        return rows

    def _get_budget_income_rows(self, program, selected_year, budget_type):
        if budget_type not in self._BUDGET_INCOME_SECTION_METADATA:
            return []
        budget_lines = self.env["tenenet.project.budget.line"].search(
            [
                ("year", "=", selected_year),
                ("budget_type", "=", budget_type),
                ("program_id", "=", program.id),
                ("amount", "!=", 0.0),
            ],
            order="project_id, sequence, id",
        )
        rows = []
        for line in budget_lines:
            values = defaultdict(float, line._get_effective_month_amounts())
            if not any(values.values()) and not line.has_explicit_month_plan:
                continue
            rows.append({
                "budget_line": line,
                "project": line.project_id,
                "name": self._get_budget_income_detail_label(line),
                "values": values,
                "value_bundle": self._value_bundle(values),
            })
        rows.sort(key=lambda row: (row["name"] or "").lower())
        return rows

    def _get_program_income_override_rows(self, program, selected_year):
        rows_by_project = {
            row["project"].id: {
                "project": row["project"],
                "name": row["name"],
                "values": self._copy_month_values(row["values"]),
                "value_bundle": self._value_bundle(row["values"]),
            }
            for row in self._get_project_income_rows(program, selected_year)
        }
        project_ids = set(rows_by_project)

        if self._is_admin_tenenet_program(program):
            project_ids.update(
                self.env["tenenet.project.budget.line"].search([
                    ("year", "=", selected_year),
                    ("budget_type", "=", "pausal"),
                    ("project_id.is_tenenet_internal", "=", False),
                ]).mapped("project_id").ids
            )
        else:
            project_ids.update(
                self.env["tenenet.project"].with_context(active_test=False).search([
                    ("reporting_program_id", "=", program.id),
                ]).ids
            )

        override_rows = self._program_override_rows(selected_year, program)
        for row_key in override_rows:
            if not row_key.startswith("income:"):
                continue
            try:
                project_ids.add(int(row_key.split(":", 1)[1]))
            except (TypeError, ValueError):
                continue

        rows = []
        for project in self.env["tenenet.project"].with_context(active_test=False).browse(sorted(project_ids)).exists():
            rows.append(
                rows_by_project.get(project.id, {
                    "project": project,
                    "name": self._get_project_line_name(project),
                    "values": self._zero_by_month(),
                })
            )
        rows.sort(key=lambda row: (row["name"] or "").lower())
        return rows

    def _make_income_row(self, project, values):
        return {
            "row_key": f"income:{project.id}",
            "project_id": project.id,
            "project": project,
            "row_label": project.display_name,
            "row_type": "income",
            "section_label": "Príjmy",
            "program": self._get_program_label(project),
            "project_label": project.display_name,
            "sequence": 100,
            "values": defaultdict(float, values),
            "value_bundle": self._value_bundle(values),
        }

    def _get_income_rows(self, selected_year):
        rows = []
        by_project = {}
        receipts = self.env["tenenet.project.receipt"].search(
            [("year", "=", selected_year)],
            order="project_id, date_received, id",
        )
        for receipt in receipts:
            project = receipt.project_id
            bucket = by_project.setdefault(project.id, {"project": project, "values": defaultdict(float)})
            for month, amount in self._get_receipt_month_values(receipt).items():
                bucket["values"][month] += amount
        cashflows = self.env["tenenet.project.cashflow"].search(
            [("receipt_year", "=", selected_year)],
            order="project_id, receipt_id, date_start",
        )
        replaced_receipt_ids = set()
        for cashflow in cashflows:
            project = cashflow.project_id
            bucket = by_project.setdefault(project.id, {"project": project, "values": defaultdict(float)})
            if cashflow.receipt_id.id not in replaced_receipt_ids and (receipt_values := self._get_receipt_month_values(cashflow.receipt_id)):
                for month in receipt_values:
                    bucket["values"][month] -= receipt_values[month]
                replaced_receipt_ids.add(cashflow.receipt_id.id)
            bucket["values"][cashflow.month] += cashflow.amount or 0.0
        for bucket in by_project.values():
            rows.append(self._make_income_row(bucket["project"], bucket["values"]))
        return sorted(rows, key=lambda row: ((row["program"] or "").lower(), row["row_label"].lower()))

    def _get_receipt_month_values(self, receipt):
        if receipt.cashflow_ids:
            return {}
        if not receipt.amount or not receipt.date_received or not receipt.year:
            return {}
        month_numbers = list(range(receipt.date_received.month, 13))
        if not month_numbers:
            return {}
        currency = receipt.currency_id or self.env.company.currency_id
        monthly_amount = currency.round(receipt.amount / len(month_numbers))
        assigned_amount = 0.0
        values = {}
        for index, month in enumerate(month_numbers, start=1):
            if index == len(month_numbers):
                values[month] = currency.round(receipt.amount - assigned_amount)
            else:
                values[month] = monthly_amount
                assigned_amount += monthly_amount
        return values

    def _get_sales_rows(self, program, selected_year):
        entry_model = self.env["tenenet.program.sales.entry"]
        labels = dict(entry_model._fields["sale_type"].selection)
        entries = entry_model.search(
            [("program_id", "=", program.id), ("year", "=", selected_year)],
            order="sale_type, period",
        )
        buckets = {}
        for entry in entries:
            bucket = buckets.setdefault(
                entry.sale_type,
                {
                    "row_key": f"sales_{entry.sale_type}",
                    "name": labels.get(entry.sale_type, entry.sale_type),
                    "values": defaultdict(float),
                    "value_bundle": self._value_bundle(),
                },
            )
            bucket["values"][entry.month] += entry.amount or 0.0
        return list(buckets.values())

    def _get_fundraising_rows(self, program, selected_year):
        entries = self.env["tenenet.fundraising.entry"].search(
            [("program_id", "=", program.id), ("year", "=", selected_year)],
            order="campaign_id, date_received",
        )
        campaign_values = {}
        for entry in entries:
            campaign = entry.campaign_id
            bucket = campaign_values.setdefault(
                campaign.id,
                {
                    "campaign": campaign,
                    "name": campaign.display_name,
                    "values": defaultdict(float),
                    "value_bundle": self._value_bundle(),
                },
            )
            bucket["values"][entry.month] += entry.amount or 0.0
        rows = [row for row in campaign_values.values() if any(row["values"].values())]
        rows.sort(key=lambda row: (row["name"] or "").lower())
        return rows

    def _get_program_labor_cost_rows(self, program, selected_year):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        internal_wage_by_assignment_month = self._get_internal_wage_by_assignment_month(
            selected_year,
            program=program,
        )
        timesheets = self.env["tenenet.project.timesheet"].with_context(active_test=False).search(
            [
                ("project_id.reporting_program_id", "=", program.id),
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ],
            order="project_id, period",
        )
        project_values = {}
        for timesheet in timesheets:
            project = timesheet.project_id
            bucket = project_values.setdefault(
                project.id,
                {"project": project, "name": self._get_project_line_name(project), "values": defaultdict(float)},
            )
            covered_amount = max(
                0.0,
                (timesheet.gross_salary or 0.0)
                - internal_wage_by_assignment_month.get(
                    (timesheet.assignment_id.id, timesheet.period.month),
                    0.0,
                ),
            )
            bucket["values"][timesheet.period.month] -= covered_amount
        rows = [row for row in project_values.values() if any(row["values"].values())]
        rows.sort(key=lambda row: (row["name"] or "").lower())
        return rows

    def _get_internal_expense_amount(self, expense):
        if expense.category in ("wage", "leave", "residual_wage"):
            return expense.cost_hm or 0.0
        return expense.expense_amount or expense.cost_ccp or 0.0

    def _get_internal_expense_project(self, expense):
        return expense.source_project_id or expense.source_assignment_id.project_id

    def _get_year_internal_expenses(self, selected_year):
        return self.env["tenenet.internal.expense"].search(
            [
                ("period", ">=", date(selected_year, 1, 1)),
                ("period", "<=", date(selected_year, 12, 31)),
            ],
            order="employee_id, period, id",
        )

    def _get_internal_wage_by_assignment_month(self, selected_year, program=None):
        wage_by_assignment_month = defaultdict(float)
        expenses = self._get_year_internal_expenses(selected_year).filtered(
            lambda exp: exp.category == "wage" and exp.source_assignment_id
        )
        for expense in expenses:
            project = self._get_internal_expense_project(expense)
            if (
                program
                and project
                and project.reporting_program_id != program
            ):
                continue
            wage_by_assignment_month[(expense.source_assignment_id.id, expense.period.month)] += (
                expense.cost_hm or 0.0
            )
        return wage_by_assignment_month

    def _get_program_project_expense_values(self, program, selected_year):
        values = self._zero_by_month()
        expenses = self.env["tenenet.project.expense"].search(
            [
                ("project_id.reporting_program_id", "=", program.id),
                ("date", ">=", date(selected_year, 1, 1)),
                ("date", "<=", date(selected_year, 12, 31)),
                ("charged_to", "=", "project"),
            ],
            order="project_id, date, id",
        )
        for expense in expenses:
            values[expense.date.month] -= expense.amount or 0.0
        return values

    def _get_admin_labor_cost_by_project_and_employee(self, selected_year):
        expenses = self._get_year_internal_expenses(selected_year)
        project_rows = {}
        for expense in expenses:
            project = self._get_internal_expense_project(expense)
            if not project or expense.employee_id.is_mgmt:
                continue

            employee = expense.employee_id
            project_bucket = project_rows.setdefault(
                project.id,
                {
                    "project": project,
                    "name": self._get_project_line_name(project),
                    "values": defaultdict(float),
                    "employee_rows": [],
                },
            )
            employee_rows_by_id = project_bucket.setdefault("_employee_rows_by_id", {})
            employee_bucket = employee_rows_by_id.setdefault(
                employee.id,
                {
                    "employee": employee,
                    "name": employee.display_name,
                    "values": defaultdict(float),
                },
            )
            amount = self._get_internal_expense_amount(expense)
            if not amount:
                continue
            project_bucket["values"][expense.period.month] -= amount
            employee_bucket["values"][expense.period.month] -= amount

        rows = []
        for bucket in project_rows.values():
            employee_rows = list(bucket.pop("_employee_rows_by_id").values())
            employee_rows = [row for row in employee_rows if any(row["values"].values())]
            employee_rows.sort(key=lambda row: (row["name"] or "").lower())
            if any(bucket["values"].values()) or employee_rows:
                bucket["employee_rows"] = employee_rows
                rows.append(bucket)
        rows.sort(key=lambda row: (row["name"] or "").lower())
        return rows

    def _get_admin_non_project_expense_rows(self, selected_year):
        expenses = self._get_year_internal_expenses(selected_year)
        rows = {}
        for expense in expenses:
            project = self._get_internal_expense_project(expense)
            if project or expense.employee_id.is_mgmt:
                continue
            employee = expense.employee_id
            bucket = rows.setdefault(
                employee.id,
                {
                    "employee": employee,
                    "name": employee.display_name,
                    "values": defaultdict(float),
                },
            )
            bucket["values"][expense.period.month] -= self._get_internal_expense_amount(expense)
        result = [row for row in rows.values() if any(row["values"].values())]
        result.sort(key=lambda row: (row["name"] or "").lower())
        return result

    def _get_admin_mgmt_labor(self, selected_year):
        values = self._zero_by_month()
        expenses = self._get_year_internal_expenses(selected_year).filtered(
            lambda exp: exp.employee_id.is_mgmt
        )
        for expense in expenses:
            project = self._get_internal_expense_project(expense)
            if project:
                continue
            values[expense.period.month] -= self._get_internal_expense_amount(expense)
        return values

    def _get_operating_cost_by_month(self, program, selected_year):
        values = defaultdict(float)
        allocations = self.env["tenenet.operating.cost.allocation"].search(
            [("program_id", "=", program.id), ("year", "=", selected_year)]
        )
        for allocation in allocations:
            values[allocation.month] -= allocation.amount or 0.0
        return values

    def _legacy_trzby_override(self, override_rows):
        return override_rows.get("sales_legacy_unclassified") or override_rows.get("trzby")

    def _legacy_admin_override(self, override_rows):
        admin_values = self._zero_by_month()
        for row_key in ("admin_tenenet_cost", "support_admin", "management"):
            row = override_rows.get(row_key)
            if not row:
                continue
            admin_values = self._sum_month_dicts(admin_values, row.get("values") or {})
        return {"values": admin_values}

    def _get_admin_cost_detail_rows(self, program, selected_year):
        if self._is_admin_tenenet_program(program):
            return []
        rows = {}
        expenses = self._get_year_internal_expenses(selected_year)
        for expense in expenses:
            project = self._get_internal_expense_project(expense)
            if not project or project.reporting_program_id != program:
                continue
            employee = expense.employee_id
            bucket = rows.setdefault(
                employee.id,
                {
                    "employee": employee,
                    "name": employee.display_name,
                    "values": defaultdict(float),
                },
            )
            bucket["values"][expense.period.month] -= self._get_internal_expense_amount(expense)
        return sorted(rows.values(), key=lambda row: (row["name"] or "").lower())

    def _get_admin_manual_detail_row(self, override_rows):
        values = self._zero_by_month()
        for row_key in ("admin_tenenet_cost", "support_admin", "management"):
            row = override_rows.get(row_key)
            if not row:
                continue
            row_values = row.get("values") or {}
            manual_months = row.get("manual_months") or {}
            for month in range(1, 13):
                if manual_months.get(month):
                    values[month] += row_values.get(month, 0.0)
        if not any(values.values()):
            return None
        return {
            "name": "Manuálna korekcia",
            "values": values,
            "is_manual": True,
        }

    def _get_admin_labor_mgmt_override_row(self, override_rows):
        labor_mgmt_row = override_rows.get("labor_mgmt")
        if labor_mgmt_row:
            return labor_mgmt_row
        legacy_values = self._legacy_admin_override(override_rows)["values"]
        if not any(legacy_values.values()):
            return None
        return {
            "values": legacy_values,
            "manual_months": {month: abs(legacy_values.get(month, 0.0)) > 0.00001 for month in range(1, 13)},
        }

    def _get_program_row_spec_metadata(self, program):
        if not self._is_admin_tenenet_program(program):
            return self._ROW_SPEC_METADATA
        return {
            "projects_total": {
                **self._ROW_SPEC_METADATA["projects_total"],
                "row_label": "Paušály",
            },
            "operating_income": self._ROW_SPEC_METADATA["operating_income"],
            "income_total": self._ROW_SPEC_METADATA["income_total"],
            "labor_cost": {
                **self._ROW_SPEC_METADATA["labor_cost"],
                "row_label": "Mzdové náklady",
            },
            "labor_non_project": self._ROW_SPEC_METADATA["labor_non_project"],
            "labor_mgmt": self._ROW_SPEC_METADATA["labor_mgmt"],
            "operating": self._ROW_SPEC_METADATA["operating"],
            "final_result": self._ROW_SPEC_METADATA["final_result"],
        }

    def _build_program_override_row_specs(self, program, selected_year):
        values = self._get_program_report_values(program, selected_year)
        row_specs = []
        for index, row in enumerate(self._get_program_income_override_rows(program, selected_year), start=1):
            row_specs.append({
                "program_id": program.id,
                "row_key": f"income:{row['project'].id}",
                "row_label": "Paušály" if self._is_admin_tenenet_program(program) else "Projekty",
                "section_label": "Príjmy",
                "project_label": row["name"],
                "sequence": 100 + index,
                "values": self._copy_month_values(row["values"]),
                "is_editable": True,
            })
        for row_key, metadata in self._get_program_row_spec_metadata(program).items():
            row_specs.append({
                "program_id": program.id,
                "row_key": row_key,
                "row_label": metadata["row_label"],
                "section_label": metadata["section_label"],
                "project_label": "",
                "sequence": metadata["sequence"],
                "values": self._copy_month_values(values[row_key]),
                "is_editable": metadata["is_editable"],
            })
        return row_specs

    def _get_editable_program_row_specs(self, selected_year):
        row_specs = []
        for program in self._get_report_programs():
            row_specs.extend(self._build_program_override_row_specs(program, selected_year))
        return row_specs

    def _get_admin_tenenet_report_values(self, program, selected_year):
        override_rows = self._program_override_rows(selected_year, program)
        project_rows = []
        for row in self._get_admin_pausal_income_rows(program, selected_year):
            row_copy = dict(row)
            row_values = self._override_month_values(
                row_copy["values"],
                override_rows.get(f"income:{row_copy['project'].id}"),
            )
            row_copy["values"] = row_values
            row_copy["value_bundle"] = self._value_bundle(row_values)
            project_rows.append(row_copy)

        projects_total = self._sum_month_value_bundles(*(row["value_bundle"] for row in project_rows))
        operating_income = self._predict_row_bundle(
            self._zero_by_month(),
            selected_year,
            override_row=override_rows.get("operating_income"),
        )
        income_total = self._sum_month_value_bundles(projects_total, operating_income)

        labor_project_rows = self._predict_report_rows(
            self._get_admin_labor_cost_by_project_and_employee(selected_year),
            selected_year,
            nested_keys=("employee_rows",),
        )
        labor_non_project_rows = self._predict_report_rows(
            self._get_admin_non_project_expense_rows(selected_year),
            selected_year,
        )
        labor_cost = self._sum_month_value_bundles(*(row["value_bundle"] for row in labor_project_rows))
        labor_non_project = self._sum_month_value_bundles(*(row["value_bundle"] for row in labor_non_project_rows))
        labor_mgmt = self._predict_row_bundle(
            self._get_admin_mgmt_labor(selected_year),
            selected_year,
            override_row=self._get_admin_labor_mgmt_override_row(override_rows),
        )
        operating = self._predict_row_bundle(
            self._get_operating_cost_by_month(program, selected_year),
            selected_year,
        )
        pre_admin_result = self._sum_month_value_bundles(income_total, labor_cost, labor_non_project, labor_mgmt)
        final_result = self._sum_month_value_bundles(pre_admin_result, operating)

        return {
            "project_rows": project_rows,
            "budget_labor_income_rows": [],
            "budget_other_income_rows": [],
            "sales_rows": [],
            "fundraising_rows": [],
            "labor_project_rows": labor_project_rows,
            "labor_non_project_rows": labor_non_project_rows,
            "admin_cost_detail_rows": [],
            "projects_total": projects_total,
            "budget_labor_income_total": self._value_bundle(),
            "budget_other_income_total": self._value_bundle(),
            "sales_cash_register": self._value_bundle(),
            "sales_individual": self._value_bundle(),
            "sales_invoice": self._value_bundle(),
            "sales_legacy_unclassified": self._value_bundle(),
            "sales_total": self._value_bundle(),
            "fundraising_individual": self._value_bundle(),
            "fundraising_corporate": self._value_bundle(),
            "fundraising_total": self._value_bundle(),
            "operating_income": operating_income,
            "income_total": income_total,
            "labor_cost": labor_cost,
            "labor_non_project": labor_non_project,
            "labor_mgmt": labor_mgmt,
            "stravne": self._value_bundle(),
            "labor_coverage": self._sum_month_value_bundles(income_total, labor_cost),
            "pre_admin_result": pre_admin_result,
            "admin_tenenet_cost": self._value_bundle(),
            "operating": operating,
            "final_result": final_result,
        }

    def _get_program_report_values(self, program, selected_year):
        if self._is_admin_tenenet_program(program):
            return self._get_admin_tenenet_report_values(program, selected_year)

        override_rows = self._program_override_rows(selected_year, program)
        budget_labor_income_rows = self._get_budget_income_rows(program, selected_year, "labor")
        service_income_rows = self._get_service_income_budget_rows(program, selected_year)
        project_rows = self._predict_report_rows(
            self._get_project_income_rows(program, selected_year, override_rows=override_rows),
            selected_year,
            override_resolver=lambda row: override_rows.get(f"income:{row['project'].id}"),
            nested_keys=("detail_rows",),
        )
        project_rows = [
            row for row in project_rows
            if self._has_nonzero_month_values(row["value_bundle"]) or row.get("detail_rows")
        ]
        sales_rows = self._get_sales_rows(program, selected_year)
        fundraising_rows = self._predict_report_rows(self._get_fundraising_rows(program, selected_year), selected_year)
        labor_project_rows = self._predict_report_rows(self._get_program_labor_cost_rows(program, selected_year), selected_year)
        admin_cost_detail_rows = self._predict_report_rows(self._get_admin_cost_detail_rows(program, selected_year), selected_year)
        admin_manual_detail_row = self._get_admin_manual_detail_row(override_rows)
        if admin_manual_detail_row:
            admin_manual_detail_row["value_bundle"] = self._value_bundle(admin_manual_detail_row["values"])
            admin_cost_detail_rows.append(admin_manual_detail_row)

        project_income = self._sum_month_value_bundles(*(row["value_bundle"] for row in project_rows))

        sales_values = {
            "sales_cash_register": self._value_bundle(),
            "sales_individual": self._value_bundle(),
            "sales_invoice": self._value_bundle(),
            "sales_legacy_unclassified": self._value_bundle(),
        }
        for row in sales_rows:
            sales_values[row["row_key"]] = self._value_bundle(row["values"])
        for row in service_income_rows:
            if row["row_key"] not in {"sales_individual", "sales_invoice"}:
                continue
            sales_values[row["row_key"]] = self._sum_month_value_bundles(
                sales_values.get(row["row_key"], self._value_bundle()),
                row["value_bundle"],
            )
        sales_values["sales_cash_register"] = self._predict_row_bundle(
            sales_values["sales_cash_register"],
            selected_year,
            override_row=override_rows.get("sales_cash_register"),
        )
        sales_values["sales_invoice"] = self._predict_row_bundle(
            sales_values["sales_invoice"],
            selected_year,
            override_row=override_rows.get("sales_invoice"),
        )
        sales_values["sales_legacy_unclassified"] = self._predict_row_bundle(
            sales_values["sales_legacy_unclassified"],
            selected_year,
            override_row=self._legacy_trzby_override(override_rows),
        )

        sales_total = self._sum_month_value_bundles(
            sales_values["sales_cash_register"],
            sales_values["sales_individual"],
            sales_values["sales_invoice"],
            sales_values["sales_legacy_unclassified"],
        )
        fundraising_individual = self._sum_month_value_bundles(*(
            row["value_bundle"] for row in service_income_rows if row["row_key"] == "fundraising_individual"
        ))
        fundraising_corporate = self._sum_month_value_bundles(*(
            row["value_bundle"] for row in service_income_rows if row["row_key"] == "fundraising_corporate"
        ))
        fundraising_total = self._sum_month_value_bundles(
            fundraising_individual,
            fundraising_corporate,
            *(row["value_bundle"] for row in fundraising_rows),
        )
        income_total = self._sum_month_value_bundles(
            project_income,
            sales_total,
            fundraising_total,
        )
        labor_cost = self._sum_month_value_bundles(*(row["value_bundle"] for row in labor_project_rows))
        stravne = self._predict_row_bundle(
            self._get_program_project_expense_values(program, selected_year),
            selected_year,
            override_row=override_rows.get("stravne"),
        )
        payroll_cover_total = self._sum_month_value_bundles(
            *(row["value_bundle"] for row in budget_labor_income_rows),
            *(row["value_bundle"] for row in service_income_rows if row["can_cover_payroll"]),
        )
        labor_coverage = self._sum_month_value_bundles(payroll_cover_total, labor_cost)
        pre_admin_result = self._sum_month_value_bundles(income_total, labor_cost, stravne)
        admin_tenenet_cost = self._sum_month_value_bundles(*(row["value_bundle"] for row in admin_cost_detail_rows))
        operating = self._predict_row_bundle(
            self._get_operating_cost_by_month(program, selected_year),
            selected_year,
        )
        final_result = self._sum_month_value_bundles(pre_admin_result, admin_tenenet_cost, operating)

        return {
            "project_rows": project_rows,
            "budget_labor_income_rows": budget_labor_income_rows,
            "budget_other_income_rows": [],
            "sales_rows": sales_rows,
            "fundraising_rows": fundraising_rows,
            "labor_project_rows": labor_project_rows,
            "labor_non_project_rows": [],
            "admin_cost_detail_rows": admin_cost_detail_rows,
            "projects_total": project_income,
            "budget_labor_income_total": self._sum_month_value_bundles(*(row["value_bundle"] for row in budget_labor_income_rows)),
            "budget_other_income_total": self._value_bundle(),
            "sales_cash_register": sales_values["sales_cash_register"],
            "sales_individual": sales_values["sales_individual"],
            "sales_invoice": sales_values["sales_invoice"],
            "sales_legacy_unclassified": sales_values["sales_legacy_unclassified"],
            "sales_total": sales_total,
            "fundraising_individual": fundraising_individual,
            "fundraising_corporate": fundraising_corporate,
            "fundraising_total": fundraising_total,
            "operating_income": self._zero_by_month(),
            "income_total": income_total,
            "labor_cost": labor_cost,
            "labor_non_project": self._value_bundle(),
            "labor_mgmt": self._value_bundle(),
            "stravne": stravne,
            "labor_coverage": labor_coverage,
            "pre_admin_result": pre_admin_result,
            "admin_tenenet_cost": admin_tenenet_cost,
            "operating": operating,
            "final_result": final_result,
        }
