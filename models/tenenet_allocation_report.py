from collections import defaultdict
from datetime import date

from odoo import fields, models


class TenenetAllocationReportHandler(models.AbstractModel):
    _name = "tenenet.allocation.report.handler"
    _inherit = ["account.report.custom.handler"]
    _description = "TENENET Allocation Report Handler"

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        custom_display_config = options["custom_display_config"]
        custom_display_config["css_custom_class"] = (
            custom_display_config.get("css_custom_class", "") + " tenenet_allocation_report"
        ).strip()
        custom_display_config.setdefault("components", {})["AccountReportFilters"] = (
            "TenenetAllocationReportFilters"
        )

        selected_employee = self._get_selected_employee(previous_options)
        options["employee_ids"] = [selected_employee.id] if selected_employee else []
        options["selected_employee_name"] = selected_employee.display_name if selected_employee else "Zamestnanec"

        selected_year = self._get_selected_year(options)
        self._set_year_options(options, selected_year)

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        employee = self._get_selected_employee(options)
        if not employee:
            return []

        year = self._get_selected_year(options)
        timesheets = self._get_employee_year_timesheets(employee, year)
        utilizations = self._get_employee_year_utilizations(employee, year)

        util_by_month = {util.period.month: util for util in utilizations}

        capacity_by_month = defaultdict(float)
        holidays_by_month = defaultdict(float)
        for month in range(1, 13):
            util = util_by_month.get(month)
            if util:
                capacity_by_month[month] = util.capacity_hours or 0.0
                holidays_by_month[month] = util.hours_holidays or 0.0

        net_capacity_by_month = {
            m: capacity_by_month[m] - holidays_by_month[m]
            for m in range(1, 13)
        }

        lines = []
        emp_id = employee.id

        lines.append((0, self._build_report_line(
            report, options,
            "Hodiny za mesiac (vrátane sviatkov)",
            capacity_by_month, "float", 2,
            f"alloc_{emp_id}_capacity_incl",
        )))
        lines.append((0, self._build_report_line(
            report, options,
            "Hodiny za mesiac",
            net_capacity_by_month, "float", 2,
            f"alloc_{emp_id}_capacity_net",
        )))

        gross_by_month = self._aggregate_field_by_month(timesheets, "gross_salary")
        deductions_by_month = self._aggregate_field_by_month(timesheets, "deductions")
        ccp_by_month = self._aggregate_field_by_month(timesheets, "total_labor_cost")
        hours_proj_by_month = self._aggregate_field_by_month(timesheets, "hours_project_total")
        hours_holidays_by_month = self._aggregate_field_by_month(timesheets, "hours_holidays")
        hours_vacation_by_month = self._aggregate_field_by_month(timesheets, "hours_vacation")
        hours_doctor_by_month = self._aggregate_field_by_month(timesheets, "hours_doctor")

        lines.append((0, self._build_report_line(
            report, options, "Hrubá mzda", gross_by_month, "monetary", 2,
            f"alloc_{emp_id}_gross_salary",
        )))
        lines.append((0, self._build_report_line(
            report, options, "Odvody", deductions_by_month, "monetary", 2,
            f"alloc_{emp_id}_deductions",
        )))
        lines.append((0, self._build_report_line(
            report, options, "CCP", ccp_by_month, "monetary", 2,
            f"alloc_{emp_id}_ccp",
        )))
        lines.append((0, self._build_report_line(
            report, options, "Odpracované hodiny", hours_proj_by_month, "float", 2,
            f"alloc_{emp_id}_hours_project",
        )))
        lines.append((0, self._build_report_line(
            report, options, "Platené sviatky", hours_holidays_by_month, "float", 2,
            f"alloc_{emp_id}_hours_holidays",
        )))
        lines.append((0, self._build_report_line(
            report, options, "Dovolenka", hours_vacation_by_month, "float", 2,
            f"alloc_{emp_id}_hours_vacation",
        )))
        lines.append((0, self._build_report_line(
            report, options, "Lekár", hours_doctor_by_month, "float", 2,
            f"alloc_{emp_id}_hours_doctor",
        )))

        project_groups = self._group_timesheets_by_project(timesheets)
        regular_projects = sorted(
            [p for p in project_groups if not p.is_tenenet_internal],
            key=lambda p: (p.name or "").lower(),
        )
        internal_projects = [p for p in project_groups if p.is_tenenet_internal]
        sorted_projects = regular_projects + internal_projects

        for project in sorted_projects:
            proj_timesheets = project_groups[project]
            lines.append((0, {
                "id": report._get_generic_line_id(
                    "tenenet.project", project.id,
                    markup=f"alloc_{emp_id}_proj_header",
                ),
                "name": project.display_name or project.name or "",
                "columns": self._build_empty_columns(report, options),
                "level": 1,
            }))

            proj_name = project.name or ""
            proj_gross = self._aggregate_field_by_month(proj_timesheets, "gross_salary")
            proj_deductions = self._aggregate_field_by_month(proj_timesheets, "deductions")
            proj_ccp = self._aggregate_field_by_month(proj_timesheets, "total_labor_cost")
            proj_hours = self._aggregate_field_by_month(proj_timesheets, "hours_project_total")

            lines.append((0, self._build_report_line(
                report, options, f"{proj_name} - Hrubá mzda", proj_gross, "monetary", 3,
                f"alloc_{emp_id}_proj_{project.id}_gross",
            )))
            lines.append((0, self._build_report_line(
                report, options, f"{proj_name} - Odvody", proj_deductions, "monetary", 3,
                f"alloc_{emp_id}_proj_{project.id}_deductions",
            )))
            lines.append((0, self._build_report_line(
                report, options, f"{proj_name} - CCP", proj_ccp, "monetary", 3,
                f"alloc_{emp_id}_proj_{project.id}_ccp",
            )))
            lines.append((0, self._build_report_line(
                report, options, f"{proj_name} - Odpracované hodiny", proj_hours, "float", 3,
                f"alloc_{emp_id}_proj_{project.id}_hours",
            )))

        empty_values = defaultdict(float)
        lines.append((0, self._build_report_line(
            report, options, "Náhrady za dovolenku", empty_values, "monetary", 2,
            f"alloc_{emp_id}_placeholder_vacation",
        )))
        lines.append((0, self._build_report_line(
            report, options, "Ošetrenie u lekára - náhrady", empty_values, "monetary", 2,
            f"alloc_{emp_id}_placeholder_doctor",
        )))
        lines.append((0, self._build_report_line(
            report, options, "Finančný príspevok za stravu - náklady", empty_values, "monetary", 2,
            f"alloc_{emp_id}_placeholder_meal",
        )))

        return lines

    def _get_selected_employee(self, options):
        employee_ids = (options or {}).get("employee_ids") or []
        employee_id = employee_ids[:1]
        if employee_id:
            return self.env["hr.employee"].browse(employee_id[0]).exists()
        return self._get_default_employee()

    def _get_default_employee(self):
        Timesheet = self.env["tenenet.project.timesheet"]
        first_ts = Timesheet.search([], order="employee_id, period", limit=1)
        if first_ts:
            return first_ts.employee_id
        return self.env["hr.employee"].search([], order="name", limit=1)

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

    def _get_employee_year_timesheets(self, employee, year):
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        return self.env["tenenet.project.timesheet"].search(
            [
                ("employee_id", "=", employee.id),
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ],
            order="project_id, period",
        )

    def _get_employee_year_utilizations(self, employee, year):
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        return self.env["tenenet.utilization"].search(
            [
                ("employee_id", "=", employee.id),
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ]
        )

    def _aggregate_field_by_month(self, timesheets, field):
        result = defaultdict(float)
        for ts in timesheets:
            result[ts.period.month] += getattr(ts, field) or 0.0
        return result

    def _group_timesheets_by_project(self, timesheets):
        project_to_record = {}
        project_map = {}
        for ts in timesheets:
            project = ts.project_id
            pid = project.id
            if pid not in project_map:
                project_to_record[pid] = project
                project_map[pid] = self.env["tenenet.project.timesheet"]
            project_map[pid] |= ts
        return {project_to_record[pid]: tss for pid, tss in project_map.items()}

    def _build_report_line(self, report, options, name, monthly_values, figure_type, level, line_id_markup):
        return {
            "id": report._get_generic_line_id(None, None, markup=line_id_markup),
            "name": name,
            "columns": self._build_allocation_columns(report, options, monthly_values, figure_type),
            "level": level,
        }

    def _build_allocation_columns(self, report, options, monthly_values, figure_type):
        columns = []
        for column in options["columns"]:
            expression_label = column["expression_label"]
            if expression_label == "metric_label":
                column_value = ""
                column_figure_type = "string"
            elif expression_label == "h1_total":
                column_value = sum(monthly_values.get(m, 0.0) for m in range(1, 7))
                column_figure_type = figure_type
            elif expression_label == "year_total":
                column_value = sum(monthly_values.get(m, 0.0) for m in range(1, 13))
                column_figure_type = figure_type
            else:
                month_number = int(expression_label.split("_")[1])
                column_value = monthly_values.get(month_number, 0.0)
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

    def _build_empty_columns(self, report, options):
        columns = []
        for column in options["columns"]:
            columns.append(
                report._build_column_dict(
                    "",
                    {**column, "figure_type": "string"},
                    options=options,
                )
            )
        return columns
