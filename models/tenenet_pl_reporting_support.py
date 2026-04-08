from collections import defaultdict
from datetime import date

from odoo import fields, models


class TenenetPLReportingSupport(models.AbstractModel):
    _name = "tenenet.pl.reporting.support"
    _description = "TENENET P&L Reporting Support"

    _ROW_SPEC_METADATA = {
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

    def _sum_month_dicts(self, *value_maps):
        result = defaultdict(float)
        for month in range(1, 13):
            result[month] = sum((values or {}).get(month, 0.0) for values in value_maps)
        return result

    def _copy_month_values(self, value_map=None):
        values = defaultdict(float)
        for month in range(1, 13):
            values[month] = (value_map or {}).get(month, 0.0)
        return values

    def _override_month_values(self, base_values, override_row):
        values = self._copy_month_values(base_values)
        if not override_row:
            return values
        manual_months = override_row.get("manual_months") or {}
        for month in range(1, 13):
            if manual_months.get(month):
                values[month] = (override_row.get("values") or {}).get(month, 0.0)
        return values

    def _predict_row_values(self, base_values, selected_year, override_row=None, annual_budget=None):
        values = self._override_month_values(base_values, override_row)
        today = fields.Date.context_today(self)
        if selected_year != today.year:
            if annual_budget is not None and not any(abs(values.get(month, 0.0)) > 0.00001 for month in range(1, 13)):
                monthly_amount = annual_budget / 12.0
                for month in range(1, 13):
                    values[month] = monthly_amount
            return values

        past_months = range(1, today.month)
        future_months = range(today.month, 13)
        history = [values[month] for month in past_months if abs(values[month]) > 0.00001]
        if len(history) >= 2:
            predicted_value = sum(history) / len(history)
        elif len(history) == 1:
            predicted_value = history[0]
        elif annual_budget is not None:
            predicted_value = annual_budget / 12.0
        else:
            return values

        manual_months = (override_row or {}).get("manual_months") or {}
        for month in future_months:
            if manual_months.get(month):
                continue
            if abs(values[month]) > 0.00001:
                continue
            values[month] = predicted_value
        return values

    def _predict_report_rows(self, rows, selected_year, override_resolver=None, nested_keys=None):
        nested_keys = tuple(nested_keys or ())
        predicted_rows = []
        for row in rows:
            row_copy = dict(row)
            override_row = override_resolver(row_copy) if override_resolver else None
            row_copy["values"] = self._predict_row_values(row_copy.get("values"), selected_year, override_row=override_row)
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

    def _get_project_income_rows(self, program, selected_year):
        project_values = {}
        cashflow_rows = self._cashflow_override_rows(selected_year)
        program_override_rows = self._program_override_rows(selected_year, program)
        cashflows = self.env["tenenet.project.cashflow"].search(
            [("receipt_year", "=", selected_year)],
            order="project_id, receipt_id, date_start",
        )
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
            bucket["values"][cashflow.month] += cashflow.amount or 0.0

        rows = []
        for project_id, bucket in project_values.items():
            program_override_row = program_override_rows.get(f"income:{project_id}")
            override_row = cashflow_rows.get(f"income:{project_id}")
            values = self._copy_month_values(bucket["values"])
            if override_row:
                values = defaultdict(float, override_row.get("values") or {})
            values = self._override_month_values(values, program_override_row)
            if any(values.values()):
                rows.append({**bucket, "values": values, "detail_rows": []})

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
            line_values = defaultdict(float, project._allocate_annual_amount_by_project_plan(selected_year, line.amount))
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
            })
        result = list(rows.values())
        result.sort(key=lambda row: (row["name"] or "").lower())
        return result

    def _get_program_income_override_rows(self, program, selected_year):
        rows_by_project = {
            row["project"].id: {
                "project": row["project"],
                "name": row["name"],
                "values": self._copy_month_values(row["values"]),
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
        }

    def _get_income_rows(self, selected_year):
        rows = []
        by_project = {}
        cashflows = self.env["tenenet.project.cashflow"].search(
            [("receipt_year", "=", selected_year)],
            order="project_id, receipt_id, date_start",
        )
        for cashflow in cashflows:
            project = cashflow.project_id
            bucket = by_project.setdefault(project.id, {"project": project, "values": defaultdict(float)})
            bucket["values"][cashflow.month] += cashflow.amount or 0.0
        for bucket in by_project.values():
            rows.append(self._make_income_row(bucket["project"], bucket["values"]))
        return sorted(rows, key=lambda row: ((row["program"] or "").lower(), row["row_label"].lower()))

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
                },
            )
            bucket["values"][entry.month] += entry.amount or 0.0
        rows = [row for row in campaign_values.values() if any(row["values"].values())]
        rows.sort(key=lambda row: (row["name"] or "").lower())
        return rows

    def _get_program_labor_cost_rows(self, program, selected_year):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
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
            bucket["values"][timesheet.period.month] -= timesheet.total_labor_cost or 0.0
        rows = [row for row in project_values.values() if any(row["values"].values())]
        rows.sort(key=lambda row: (row["name"] or "").lower())
        return rows

    def _get_internal_expense_amount(self, expense):
        return expense.cost_ccp or expense.expense_amount or 0.0

    def _get_admin_labor_cost_by_project_and_employee(self, selected_year):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        timesheets = self.env["tenenet.project.timesheet"].with_context(active_test=False).search(
            [
                ("project_id.is_tenenet_internal", "=", False),
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ],
            order="project_id, employee_id, period",
        )
        project_rows = {}
        for timesheet in timesheets:
            project = timesheet.project_id
            employee = timesheet.employee_id
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
            amount = timesheet.total_labor_cost or 0.0
            project_bucket["values"][timesheet.period.month] -= amount
            employee_bucket["values"][timesheet.period.month] -= amount

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
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        expenses = self.env["tenenet.internal.expense"].search(
            [
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ],
            order="employee_id, period",
        )
        rows = {}
        for expense in expenses:
            project = expense.source_project_id or expense.source_assignment_id.project_id
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
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        values = self._zero_by_month()
        expenses = self.env["tenenet.internal.expense"].search(
            [
                ("employee_id.is_mgmt", "=", True),
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ],
            order="employee_id, period",
        )
        for expense in expenses:
            project = expense.source_project_id or expense.source_assignment_id.project_id
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
        if not self._is_admin_tenenet_program(program):
            return []
        rows = {}
        expenses = self.env["tenenet.internal.expense"].search(
            [
                ("period", ">=", date(selected_year, 1, 1)),
                ("period", "<=", date(selected_year, 12, 31)),
            ],
            order="employee_id, period",
        )
        for expense in expenses:
            employee = expense.employee_id
            bucket = rows.setdefault(
                employee.id,
                {
                    "employee": employee,
                    "name": employee.display_name,
                    "values": defaultdict(float),
                },
            )
            bucket["values"][expense.period.month] -= expense.cost_ccp or expense.expense_amount or 0.0
        return sorted(rows.values(), key=lambda row: (row["name"] or "").lower())

    def _get_admin_manual_detail_row(self, override_rows):
        values = self._legacy_admin_override(override_rows)["values"]
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
            row_copy["values"] = self._predict_row_values(
                row_copy["values"],
                selected_year,
                override_row=override_rows.get(f"income:{row_copy['project'].id}"),
            )
            project_rows.append(row_copy)

        projects_total = self._sum_month_dicts(*(row["values"] for row in project_rows))
        operating_income = self._predict_row_values(
            self._zero_by_month(),
            selected_year,
            override_row=override_rows.get("operating_income"),
        )
        income_total = self._sum_month_dicts(projects_total, operating_income)

        labor_project_rows = self._predict_report_rows(
            self._get_admin_labor_cost_by_project_and_employee(selected_year),
            selected_year,
            nested_keys=("employee_rows",),
        )
        labor_non_project_rows = self._predict_report_rows(
            self._get_admin_non_project_expense_rows(selected_year),
            selected_year,
        )
        labor_cost = self._sum_month_dicts(*(row["values"] for row in labor_project_rows))
        labor_non_project = self._sum_month_dicts(*(row["values"] for row in labor_non_project_rows))
        labor_mgmt = self._predict_row_values(
            self._get_admin_mgmt_labor(selected_year),
            selected_year,
            override_row=self._get_admin_labor_mgmt_override_row(override_rows),
        )
        operating = self._predict_row_values(
            self._get_operating_cost_by_month(program, selected_year),
            selected_year,
        )
        pre_admin_result = self._sum_month_dicts(income_total, labor_cost, labor_non_project, labor_mgmt)
        final_result = self._sum_month_dicts(pre_admin_result, operating)

        return {
            "project_rows": project_rows,
            "sales_rows": [],
            "fundraising_rows": [],
            "labor_project_rows": labor_project_rows,
            "labor_non_project_rows": labor_non_project_rows,
            "admin_cost_detail_rows": [],
            "projects_total": projects_total,
            "sales_cash_register": self._zero_by_month(),
            "sales_invoice": self._zero_by_month(),
            "sales_legacy_unclassified": self._zero_by_month(),
            "sales_total": self._zero_by_month(),
            "fundraising_total": self._zero_by_month(),
            "operating_income": operating_income,
            "income_total": income_total,
            "labor_cost": labor_cost,
            "labor_non_project": labor_non_project,
            "labor_mgmt": labor_mgmt,
            "stravne": self._zero_by_month(),
            "labor_coverage": self._sum_month_dicts(income_total, labor_cost),
            "pre_admin_result": pre_admin_result,
            "admin_tenenet_cost": self._zero_by_month(),
            "operating": operating,
            "final_result": final_result,
        }

    def _get_program_report_values(self, program, selected_year):
        if self._is_admin_tenenet_program(program):
            return self._get_admin_tenenet_report_values(program, selected_year)

        override_rows = self._program_override_rows(selected_year, program)
        project_rows = self._predict_report_rows(
            self._get_project_income_rows(program, selected_year),
            selected_year,
            override_resolver=lambda row: override_rows.get(f"income:{row['project'].id}"),
        )
        sales_rows = self._get_sales_rows(program, selected_year)
        fundraising_rows = self._predict_report_rows(self._get_fundraising_rows(program, selected_year), selected_year)
        labor_project_rows = self._predict_report_rows(self._get_program_labor_cost_rows(program, selected_year), selected_year)
        admin_cost_detail_rows = self._predict_report_rows(self._get_admin_cost_detail_rows(program, selected_year), selected_year)
        admin_manual_detail_row = self._get_admin_manual_detail_row(override_rows)
        if admin_manual_detail_row:
            admin_cost_detail_rows.append(admin_manual_detail_row)

        project_income = self._sum_month_dicts(*(row["values"] for row in project_rows))

        sales_values = {
            "sales_cash_register": self._zero_by_month(),
            "sales_invoice": self._zero_by_month(),
            "sales_legacy_unclassified": self._zero_by_month(),
        }
        for row in sales_rows:
            sales_values[row["row_key"]] = self._copy_month_values(row["values"])
        sales_values["sales_cash_register"] = self._predict_row_values(
            sales_values["sales_cash_register"],
            selected_year,
            override_row=override_rows.get("sales_cash_register"),
        )
        sales_values["sales_invoice"] = self._predict_row_values(
            sales_values["sales_invoice"],
            selected_year,
            override_row=override_rows.get("sales_invoice"),
        )
        sales_values["sales_legacy_unclassified"] = self._predict_row_values(
            sales_values["sales_legacy_unclassified"],
            selected_year,
            override_row=self._legacy_trzby_override(override_rows),
        )

        sales_total = self._sum_month_dicts(
            sales_values["sales_cash_register"],
            sales_values["sales_invoice"],
            sales_values["sales_legacy_unclassified"],
        )
        fundraising_total = self._sum_month_dicts(*(row["values"] for row in fundraising_rows))
        income_total = self._sum_month_dicts(project_income, sales_total, fundraising_total)
        labor_cost = self._sum_month_dicts(*(row["values"] for row in labor_project_rows))
        stravne = self._predict_row_values(
            self._zero_by_month(),
            selected_year,
            override_row=override_rows.get("stravne"),
        )
        labor_coverage = self._sum_month_dicts(income_total, labor_cost)
        pre_admin_result = self._sum_month_dicts(labor_coverage, stravne)
        admin_tenenet_cost = self._sum_month_dicts(*(row["values"] for row in admin_cost_detail_rows))
        operating = self._predict_row_values(
            self._get_operating_cost_by_month(program, selected_year),
            selected_year,
        )
        final_result = self._sum_month_dicts(pre_admin_result, admin_tenenet_cost, operating)

        return {
            "project_rows": project_rows,
            "sales_rows": sales_rows,
            "fundraising_rows": fundraising_rows,
            "labor_project_rows": labor_project_rows,
            "labor_non_project_rows": [],
            "admin_cost_detail_rows": admin_cost_detail_rows,
            "projects_total": project_income,
            "sales_cash_register": sales_values["sales_cash_register"],
            "sales_invoice": sales_values["sales_invoice"],
            "sales_legacy_unclassified": sales_values["sales_legacy_unclassified"],
            "sales_total": sales_total,
            "fundraising_total": fundraising_total,
            "operating_income": self._zero_by_month(),
            "income_total": income_total,
            "labor_cost": labor_cost,
            "labor_non_project": self._zero_by_month(),
            "labor_mgmt": self._zero_by_month(),
            "stravne": stravne,
            "labor_coverage": labor_coverage,
            "pre_admin_result": pre_admin_result,
            "admin_tenenet_cost": admin_tenenet_cost,
            "operating": operating,
            "final_result": final_result,
        }
