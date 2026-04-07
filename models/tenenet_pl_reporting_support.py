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
        "stravne": {
            "row_label": "Stravné a iné",
            "sequence": 520,
            "section_label": "Náklady",
            "is_editable": True,
        },
        "support_admin": {
            "row_label": "Mzdové N - podporné odd/admin",
            "sequence": 700,
            "section_label": "Náklady",
            "is_editable": True,
        },
        "management": {
            "row_label": "Mzdové N - management",
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

    def _cashflow_override_rows(self, selected_year):
        return self.env["tenenet.cashflow.global.override"].get_year_row_data(selected_year)

    def _program_override_rows(self, selected_year, program):
        return self.env["tenenet.pl.program.override"].get_year_row_data(selected_year).get(program.id, {})

    def _get_project_income_rows(self, program, selected_year):
        project_values = {}
        cashflow_rows = self._cashflow_override_rows(selected_year)
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
            override_row = cashflow_rows.get(f"income:{project_id}")
            values = self._copy_month_values(bucket["values"])
            if override_row:
                values = defaultdict(float, override_row.get("values") or {})
            if any(values.values()):
                rows.append({**bucket, "values": values})

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

    def _build_program_override_row_specs(self, program, selected_year):
        values = self._get_program_report_values(program, selected_year)
        row_specs = []
        for row_key, metadata in self._ROW_SPEC_METADATA.items():
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

    def _get_program_report_values(self, program, selected_year):
        override_rows = self._program_override_rows(selected_year, program)
        project_rows = self._get_project_income_rows(program, selected_year)
        sales_rows = self._get_sales_rows(program, selected_year)
        fundraising_rows = self._get_fundraising_rows(program, selected_year)
        labor_project_rows = self._get_program_labor_cost_rows(program, selected_year)

        project_income = self._sum_month_dicts(*(row["values"] for row in project_rows))

        sales_values = {
            "sales_cash_register": self._zero_by_month(),
            "sales_invoice": self._zero_by_month(),
            "sales_legacy_unclassified": self._zero_by_month(),
        }
        for row in sales_rows:
            sales_values[row["row_key"]] = self._copy_month_values(row["values"])
        sales_values["sales_cash_register"] = self._override_month_values(
            sales_values["sales_cash_register"],
            override_rows.get("sales_cash_register"),
        )
        sales_values["sales_invoice"] = self._override_month_values(
            sales_values["sales_invoice"],
            override_rows.get("sales_invoice"),
        )
        sales_values["sales_legacy_unclassified"] = self._override_month_values(
            sales_values["sales_legacy_unclassified"],
            self._legacy_trzby_override(override_rows),
        )

        sales_total = self._sum_month_dicts(
            sales_values["sales_cash_register"],
            sales_values["sales_invoice"],
            sales_values["sales_legacy_unclassified"],
        )
        fundraising_total = self._sum_month_dicts(*(row["values"] for row in fundraising_rows))
        income_total = self._sum_month_dicts(project_income, sales_total, fundraising_total)
        labor_cost = self._sum_month_dicts(*(row["values"] for row in labor_project_rows))
        stravne = self._override_month_values(self._zero_by_month(), override_rows.get("stravne"))
        labor_coverage = self._sum_month_dicts(income_total, labor_cost)
        pre_admin_result = self._sum_month_dicts(labor_coverage, stravne)
        support_admin = self._override_month_values(self._zero_by_month(), override_rows.get("support_admin"))
        management = self._override_month_values(self._zero_by_month(), override_rows.get("management"))
        operating = self._get_operating_cost_by_month(program, selected_year)
        final_result = self._sum_month_dicts(pre_admin_result, support_admin, management, operating)

        return {
            "project_rows": project_rows,
            "sales_rows": sales_rows,
            "fundraising_rows": fundraising_rows,
            "labor_project_rows": labor_project_rows,
            "projects_total": project_income,
            "sales_cash_register": sales_values["sales_cash_register"],
            "sales_invoice": sales_values["sales_invoice"],
            "sales_legacy_unclassified": sales_values["sales_legacy_unclassified"],
            "sales_total": sales_total,
            "fundraising_total": fundraising_total,
            "income_total": income_total,
            "labor_cost": labor_cost,
            "stravne": stravne,
            "labor_coverage": labor_coverage,
            "pre_admin_result": pre_admin_result,
            "support_admin": support_admin,
            "management": management,
            "operating": operating,
            "final_result": final_result,
        }
