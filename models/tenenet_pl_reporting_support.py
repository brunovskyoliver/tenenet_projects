from collections import defaultdict
from datetime import date

from odoo import fields, models


class TenenetPLReportingSupport(models.AbstractModel):
    _name = "tenenet.pl.reporting.support"
    _description = "TENENET P&L Reporting Support"

    _ROW_SPEC_METADATA = {
        "trzby": {"row_label": "Tržby", "sequence": 300, "section_label": "Príjmy", "project_label": "", "is_editable": True},
        "labor_cost": {
            "row_label": "Mzdové náklady - program",
            "sequence": 400,
            "section_label": "Náklady",
            "project_label": "",
            "is_editable": True,
        },
        "stravne": {
            "row_label": "Stravné a iné",
            "sequence": 500,
            "section_label": "Náklady",
            "project_label": "",
            "is_editable": True,
        },
        "pre_admin_result": {
            "row_label": "Zisk/strata - vykrytie mzdových nákladov",
            "sequence": 600,
            "section_label": "Náklady",
            "project_label": "",
            "is_editable": False,
        },
        "support_admin": {
            "row_label": "Mzdové N - podporné odd/admin",
            "sequence": 700,
            "section_label": "Náklady",
            "project_label": "",
            "is_editable": True,
        },
        "management": {
            "row_label": "Mzdové N - management",
            "sequence": 800,
            "section_label": "Náklady",
            "project_label": "",
            "is_editable": True,
        },
        "operating": {
            "row_label": "Prevádzkové náklady",
            "sequence": 900,
            "section_label": "Náklady",
            "project_label": "",
            "is_editable": True,
        },
        "final_result": {
            "row_label": "Zisk/strata - za program",
            "sequence": 1000,
            "section_label": "Náklady",
            "project_label": "",
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
        code = ""
        if "code" in project._fields:
            code = (project.code or "").strip()
        name = (project.name or "").strip() or project.display_name or ""
        return f"{code} {name}".strip() if code else name

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

    def _get_income_rows(self, selected_year):
        rows = []
        project_values = {}
        cashflows = self.env["tenenet.project.cashflow"].search(
            [("receipt_year", "=", selected_year)],
            order="project_id, receipt_id, date_start",
        )
        for cashflow in cashflows:
            project = cashflow.project_id
            bucket = project_values.setdefault(
                project.id,
                {"project": project, "values": defaultdict(float)},
            )
            bucket["values"][cashflow.month] += cashflow.amount or 0.0

        for bucket in project_values.values():
            if any(bucket["values"].values()):
                rows.append(self._make_income_row(bucket["project"], bucket["values"]))

        return sorted(rows, key=lambda row: ((row["program"] or "").lower(), row["row_label"].lower()))

    def _make_income_row(self, project, values):
        return {
            "row_key": f"income:{project.id}",
            "project_id": project.id,
            "project": project,
            "row_label": project.display_name,
            "row_type": "income",
            "section_label": "Príjmy",
            "program": ", ".join(project.program_ids.mapped("name")),
            "project_label": project.display_name,
            "sequence": 100,
            "values": defaultdict(float, values),
        }

    def _get_effective_income_rows(self, selected_year):
        forecast_rows = self._get_income_rows(selected_year)
        forecast_by_key = {row["row_key"]: row for row in forecast_rows}
        override_rows = self.env["tenenet.cashflow.global.override"].get_year_row_data(selected_year)
        effective_rows = []

        for row_key, forecast_row in forecast_by_key.items():
            row = {**forecast_row, "values": defaultdict(float, forecast_row["values"])}
            override_row = override_rows.get(row_key)
            if override_row:
                for month, amount in override_row["values"].items():
                    row["values"][month] = amount
            if any(row["values"].get(month, 0.0) for month in range(1, 13)):
                effective_rows.append(row)

        return sorted(
            effective_rows,
            key=lambda row: ((row["program"] or "").lower(), row["row_label"].lower()),
        )

    def _get_program_income_rows(self, program, selected_year):
        international_rows = []
        national_rows = []
        for income_row in self._get_effective_income_rows(selected_year):
            project = income_row["project"]
            if program not in project.program_ids:
                continue
            target = international_rows if project._is_international_by_donor() else national_rows
            target.append({
                "project": project,
                "name": self._get_project_line_name(project),
                "values": defaultdict(float, income_row["values"]),
            })
        international_rows.sort(key=lambda row: (row["name"] or "").lower())
        national_rows.sort(key=lambda row: (row["name"] or "").lower())
        return international_rows, national_rows

    def _build_program_override_row_specs(self, program, selected_year):
        values = self._get_program_report_values(program, selected_year)
        row_specs = []
        for index, row in enumerate(values["international_rows"], start=1):
            row_specs.append({
                "program_id": program.id,
                "row_key": f"income:{row['project'].id}",
                "row_label": f"Príjmy projektu - {row['name']}",
                "section_label": "Príjmy",
                "project_label": row["name"],
                "sequence": 100 + index,
                "values": self._copy_month_values(row["values"]),
                "is_editable": True,
            })
        for index, row in enumerate(values["national_rows"], start=1):
            row_specs.append({
                "program_id": program.id,
                "row_key": f"income:{row['project'].id}",
                "row_label": f"Príjmy projektu - {row['name']}",
                "section_label": "Príjmy",
                "project_label": row["name"],
                "sequence": 200 + index,
                "values": self._copy_month_values(row["values"]),
                "is_editable": True,
            })
        for index, row in enumerate(values["labor_project_rows"], start=1):
            row_specs.append({
                "program_id": program.id,
                "row_key": f"labor_project:{row['project'].id}",
                "row_label": f"Mzdové náklady projektu - {row['name']}",
                "section_label": "Náklady",
                "project_label": row["name"],
                "sequence": 400 + index,
                "values": self._copy_month_values(row["values"]),
                "is_editable": True,
            })
        for row_key, metadata in self._ROW_SPEC_METADATA.items():
            row_specs.append({
                "program_id": program.id,
                "row_key": row_key,
                "row_label": metadata["row_label"],
                "section_label": metadata["section_label"],
                "project_label": metadata["project_label"],
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

    def _get_program_labor_cost_by_month(self, program, selected_year):
        labor_project_rows = self._get_program_labor_cost_rows(program, selected_year)
        if labor_project_rows:
            return self._sum_month_dicts(*(row["values"] for row in labor_project_rows))

        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        values = defaultdict(float)
        pl_lines = self.env["tenenet.pl.line"].search(
            [
                ("program_id", "=", program.id),
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ]
        )
        for line in pl_lines:
            values[line.period.month] -= line.amount or 0.0
        return values

    def _get_program_labor_cost_rows(self, program, selected_year):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        timesheets = self.env["tenenet.project.timesheet"].with_context(active_test=False).search(
            [
                ("project_id.program_ids", "in", [program.id]),
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

    def _get_program_trzby_by_month(self, program, selected_year):
        override_rows = self.env["tenenet.pl.program.override"].get_year_row_data(selected_year)
        program_row = override_rows.get(program.id, {}).get("trzby")
        if not program_row:
            return self._zero_by_month()
        return defaultdict(float, program_row["values"])

    def _get_program_report_values(self, program, selected_year):
        override_rows = self.env["tenenet.pl.program.override"].get_year_row_data(selected_year).get(program.id, {})
        international_rows, national_rows = self._get_program_income_rows(program, selected_year)
        for row in international_rows:
            row["values"] = self._override_month_values(row["values"], override_rows.get(f"income:{row['project'].id}"))
        for row in national_rows:
            row["values"] = self._override_month_values(row["values"], override_rows.get(f"income:{row['project'].id}"))
        labor_project_rows = self._get_program_labor_cost_rows(program, selected_year)
        for row in labor_project_rows:
            row["values"] = self._override_month_values(
                row["values"],
                override_rows.get(f"labor_project:{row['project'].id}"),
            )
        international_income = self._sum_month_dicts(*(row["values"] for row in international_rows))
        national_income = self._sum_month_dicts(*(row["values"] for row in national_rows))
        trzby = self._override_month_values(self._zero_by_month(), override_rows.get("trzby"))
        prijmy_spolu = self._sum_month_dicts(international_income, national_income, trzby)
        labor_cost_base = (
            self._sum_month_dicts(*(row["values"] for row in labor_project_rows))
            if labor_project_rows
            else self._get_program_labor_cost_by_month(program, selected_year)
        )
        labor_cost = self._override_month_values(labor_cost_base, override_rows.get("labor_cost"))
        stravne = self._override_month_values(self._zero_by_month(), override_rows.get("stravne"))
        support_admin = self._override_month_values(self._zero_by_month(), override_rows.get("support_admin"))
        management = self._override_month_values(self._zero_by_month(), override_rows.get("management"))
        operating = self._override_month_values(self._zero_by_month(), override_rows.get("operating"))
        pre_admin_result = self._sum_month_dicts(prijmy_spolu, labor_cost, stravne)
        final_result = self._sum_month_dicts(pre_admin_result, support_admin, management, operating)
        prijmy_spolu = self._override_month_values(prijmy_spolu, override_rows.get("prijmy_spolu"))
        pre_admin_result = self._override_month_values(pre_admin_result, override_rows.get("pre_admin_result"))
        final_result = self._override_month_values(final_result, override_rows.get("final_result"))
        return {
            "international_rows": international_rows,
            "national_rows": national_rows,
            "international_income": international_income,
            "national_income": national_income,
            "labor_project_rows": labor_project_rows,
            "trzby": trzby,
            "prijmy_spolu": prijmy_spolu,
            "labor_cost": labor_cost,
            "stravne": stravne,
            "support_admin": support_admin,
            "management": management,
            "operating": operating,
            "pre_admin_result": pre_admin_result,
            "final_result": final_result,
        }
