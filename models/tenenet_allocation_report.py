from collections import defaultdict
from datetime import date

from odoo import fields, models


class TenenetAllocationReportHandler(models.AbstractModel):
    _name = "tenenet.allocation.report.handler"
    _inherit = ["account.report.custom.handler"]
    _description = "TENENET Allocation Report Handler"

    _TRAVEL_EXPENSE_TOKENS = ("cestovn", "travel")
    _TRAINING_EXPENSE_TOKENS = ("školen", "skolen", "training")

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        custom_display_config = options["custom_display_config"]
        custom_display_config["css_custom_class"] = (
            custom_display_config.get("css_custom_class", "") + " tenenet_allocation_report"
        ).strip()
        custom_display_config.setdefault("components", {})["AccountReportFilters"] = (
            "TenenetAllocationReportFilters"
        )

        available_employee_ids = self.env["tenenet.project"].get_report_accessible_employee_ids()
        options["available_employee_domain"] = [("id", "in", available_employee_ids or [0])]

        selected_employee = self._get_selected_employee(previous_options, available_employee_ids=available_employee_ids)
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

        gross_by_month = self._aggregate_field_by_month(timesheets, "gross_salary")
        deductions_by_month = self._aggregate_field_by_month(timesheets, "deductions")
        ccp_by_month = self._aggregate_field_by_month(timesheets, "total_labor_cost")

        lines.append((0, self._build_report_line(
            report, options,
            "Celkové rozúčtovanie",
            ccp_by_month, "monetary", 1,
            f"alloc_{emp_id}_summary_header",
        )))

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

        # ── Project sections (collapsible) ───────────────────────────────────
        internal_expenses = self._get_employee_year_internal_expenses(employee, year)
        internal_wage_by_project = self._group_internal_wage_by_project(
            internal_expenses.filtered(lambda e: e.category == "wage")
        )
        project_groups = self._group_timesheets_by_project(timesheets)
        sorted_projects = sorted(
            project_groups.keys(),
            key=lambda p: (p.name or "").lower(),
        )

        for project in sorted_projects:
            proj_timesheets = project_groups[project]
            proj_ccp = self._aggregate_field_by_month(proj_timesheets, "total_labor_cost")
            internal_wage = internal_wage_by_project.get(project.id, {})
            internal_ccp = internal_wage.get("ccp", defaultdict(float))
            proj_ccp_net = self._subtract_monthly_values(proj_ccp, internal_ccp)

            proj_line_id = report._get_generic_line_id(
                "tenenet.project", project.id,
                markup=f"alloc_{emp_id}_proj_{project.id}",
            )
            is_unfolded = bool(
                options.get("unfold_all")
                or proj_line_id in (options.get("unfolded_lines") or [])
            )
            lines.append((0, {
                "id": proj_line_id,
                "name": self._get_project_allocation_line_name(project, proj_timesheets),
                "columns": self._build_allocation_columns(report, options, proj_ccp_net, "monetary"),
                "level": 1,
                "unfoldable": True,
                "unfolded": is_unfolded,
                "expand_function": "_report_expand_unfoldable_line_alloc_project",
            }))

        # ── Interné náklady section ──────────────────────────────────────────

        lines.append((0, {
            "id": report._get_generic_line_id(None, None, markup=f"alloc_{emp_id}_internal_header"),
            "name": "Interné náklady (nezúčtované)",
            "columns": self._build_empty_columns(report, options),
            "level": 1,
        }))

        leave_expenses = internal_expenses.filtered(lambda e: e.category == "leave")
        wage_expenses = internal_expenses.filtered(lambda e: e.category in {"wage", "residual_wage"})
        expense_expenses = internal_expenses.filtered(lambda e: e.category == "expense")

        ie_leave_hm = defaultdict(float)
        ie_leave_ccp = defaultdict(float)
        for exp in leave_expenses:
            ie_leave_hm[exp.period.month] += exp.cost_hm or 0.0
            ie_leave_ccp[exp.period.month] += exp.cost_ccp or 0.0

        ie_wage_hm = defaultdict(float)
        ie_wage_ccp = defaultdict(float)
        for exp in wage_expenses:
            ie_wage_hm[exp.period.month] += exp.cost_hm or 0.0
            ie_wage_ccp[exp.period.month] += exp.cost_ccp or 0.0

        ie_travel = self._aggregate_internal_expense_bucket_by_month(
            expense_expenses,
            self._TRAVEL_EXPENSE_TOKENS,
        )
        ie_training = self._aggregate_internal_expense_bucket_by_month(
            expense_expenses,
            self._TRAINING_EXPENSE_TOKENS,
        )

        if any(ie_leave_hm.values()) or any(ie_leave_ccp.values()):
            lines.append((0, self._build_report_line(
                report, options, "Interné náklady - dovolenka (HM)",
                ie_leave_hm, "monetary", 2,
                f"alloc_{emp_id}_internal_leave_hm",
            )))
            lines.append((0, self._build_report_line(
                report, options, "Interné náklady - dovolenka (CCP)",
                ie_leave_ccp, "monetary", 2,
                f"alloc_{emp_id}_internal_leave_ccp",
            )))

        if any(ie_wage_hm.values()) or any(ie_wage_ccp.values()):
            lines.append((0, self._build_report_line(
                report, options, "Interné náklady - mzda (HM)",
                ie_wage_hm, "monetary", 2,
                f"alloc_{emp_id}_internal_wage_hm",
            )))
            lines.append((0, self._build_report_line(
                report, options, "Interné náklady - mzda (CCP)",
                ie_wage_ccp, "monetary", 2,
                f"alloc_{emp_id}_internal_wage_ccp",
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
            report, options, "Cestovné náhrady", ie_travel or empty_values, "monetary", 2,
            f"alloc_{emp_id}_internal_travel",
        )))
        lines.append((0, self._build_report_line(
            report, options, "Školenie", ie_training or empty_values, "monetary", 2,
            f"alloc_{emp_id}_internal_training",
        )))
        lines.append((0, self._build_report_line(
            report, options, "Finančný príspevok za stravu - náklady", empty_values, "monetary", 2,
            f"alloc_{emp_id}_placeholder_meal",
        )))

        return lines

    def _report_expand_unfoldable_line_alloc_project(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        employee = self._get_selected_employee(options)
        year = self._get_selected_year(options)

        project_id = report._get_res_id_from_line_id(line_dict_id, "tenenet.project")
        if not project_id or not employee:
            return {"lines": [], "offset_increment": 0, "has_more": False, "progress": progress}

        project = self.env["tenenet.project"].browse(project_id)
        lines = self._build_project_detail_lines(report, options, employee, year, project, line_dict_id)
        return {"lines": lines, "offset_increment": len(lines), "has_more": False, "progress": progress}

    def _get_project_allocation_line_name(self, project, timesheets):
        name = project.display_name or project.name or ""
        if timesheets and all(timesheets.mapped("assignment_id.settlement_only")):
            return f"{name} (iba na zúčtovanie)"
        return name

    def _build_project_detail_lines(self, report, options, employee, year, project, parent_line_id):
        emp_id = employee.id
        proj_timesheets = self._get_project_timesheets_for_employee(employee, project, year)
        internal_expenses = self._get_employee_year_internal_expenses(employee, year)
        internal_wage_by_project = self._group_internal_wage_by_project(
            internal_expenses.filtered(lambda e: e.category == "wage")
        )
        internal_wage_by_assignment = self._group_internal_wage_by_assignment(
            internal_expenses.filtered(lambda e: e.category == "wage")
        )

        proj_name = project.name or ""
        proj_gross = self._aggregate_field_by_month(proj_timesheets, "gross_salary")
        proj_deductions = self._aggregate_field_by_month(proj_timesheets, "deductions")
        proj_ccp = self._aggregate_field_by_month(proj_timesheets, "total_labor_cost")
        proj_hours = self._aggregate_field_by_month(proj_timesheets, "hours_project_total")
        settlement_timesheets = proj_timesheets.filtered(lambda ts: ts.assignment_id.settlement_only)
        settlement_ccp = self._aggregate_field_by_month(settlement_timesheets, "total_labor_cost")
        settlement_internal_ccp = defaultdict(float)
        for assignment_id in settlement_timesheets.mapped("assignment_id").ids:
            assignment_wage = internal_wage_by_assignment.get(assignment_id, {})
            assignment_ccp = assignment_wage.get("ccp", defaultdict(float))
            for month in range(1, 13):
                settlement_internal_ccp[month] += assignment_ccp.get(month, 0.0)
        settlement_ccp = self._subtract_monthly_values(settlement_ccp, settlement_internal_ccp)

        internal_wage = internal_wage_by_project.get(project.id, {})
        internal_hm = internal_wage.get("hm", defaultdict(float))
        internal_ccp = internal_wage.get("ccp", defaultdict(float))
        internal_deductions = defaultdict(float, {
            month: (internal_ccp.get(month, 0.0) - internal_hm.get(month, 0.0))
            for month in range(1, 13)
        })
        proj_gross = self._subtract_monthly_values(proj_gross, internal_hm)
        proj_deductions = self._subtract_monthly_values(proj_deductions, internal_deductions)
        proj_ccp = self._subtract_monthly_values(proj_ccp, internal_ccp)

        lines = [
            self._build_report_line(
                report, options, f"{proj_name} - Hrubá mzda", proj_gross, "monetary", 3,
                f"alloc_{emp_id}_proj_{project.id}_gross",
                parent_line_id=parent_line_id,
            ),
            self._build_report_line(
                report, options, f"{proj_name} - Odvody", proj_deductions, "monetary", 3,
                f"alloc_{emp_id}_proj_{project.id}_deductions",
                parent_line_id=parent_line_id,
            ),
            self._build_report_line(
                report, options, f"{proj_name} - CCP", proj_ccp, "monetary", 3,
                f"alloc_{emp_id}_proj_{project.id}_ccp",
                parent_line_id=parent_line_id,
            ),
            self._build_report_line(
                report, options, f"{proj_name} - Odpracované hodiny", proj_hours, "float", 3,
                f"alloc_{emp_id}_proj_{project.id}_hours",
                parent_line_id=parent_line_id,
            ),
        ]
        if any(settlement_ccp.values()):
            lines.append(self._build_report_line(
                report, options, "Mzda iba na zúčtovanie", settlement_ccp, "monetary", 3,
                f"alloc_{emp_id}_proj_{project.id}_settlement_only_wage",
                parent_line_id=parent_line_id,
            ))
        return lines

    def _get_selected_employee(self, options, available_employee_ids=None):
        allowed_employee_ids = available_employee_ids or self.env["tenenet.project"].get_report_accessible_employee_ids()
        employee_ids = (options or {}).get("employee_ids") or []
        employee_id = employee_ids[:1]
        if employee_id:
            employee = self.env["hr.employee"].browse(employee_id[0]).exists()
            if employee and employee.id in allowed_employee_ids:
                return employee
        return self._get_default_employee(allowed_employee_ids=allowed_employee_ids)

    def _get_default_employee(self, allowed_employee_ids=None):
        employee_ids = allowed_employee_ids or self.env["tenenet.project"].get_report_accessible_employee_ids()
        Timesheet = self.env["tenenet.project.timesheet"]
        first_ts = Timesheet.search(
            [("employee_id", "in", employee_ids or [0])],
            order="employee_id, period",
            limit=1,
        )
        if first_ts:
            return first_ts.employee_id
        return self.env["hr.employee"].browse((employee_ids or [False])[:1]).exists()

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
        allowed_project_ids = self.env["tenenet.project"].get_report_accessible_project_ids()
        return self.env["tenenet.project.timesheet"].search(
            [
                ("employee_id", "=", employee.id),
                ("period", ">=", year_start),
                ("period", "<=", year_end),
                ("project_id.is_tenenet_internal", "=", False),
                ("project_id", "in", allowed_project_ids or [0]),
            ],
            order="project_id, period",
        )

    def _get_project_timesheets_for_employee(self, employee, project, year):
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        allowed_project_ids = self.env["tenenet.project"].get_report_accessible_project_ids()
        return self.env["tenenet.project.timesheet"].search(
            [
                ("employee_id", "=", employee.id),
                ("project_id", "=", project.id),
                ("project_id", "in", allowed_project_ids or [0]),
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ],
            order="period",
        )

    def _get_employee_year_internal_expenses(self, employee, year):
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        return self.env["tenenet.internal.expense"].sudo().search([
            ("employee_id", "=", employee.id),
            ("period", ">=", year_start),
            ("period", "<=", year_end),
        ])

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

    def _group_internal_wage_by_project(self, wage_expenses):
        result = {}
        for exp in wage_expenses:
            project = exp.source_assignment_id.project_id if exp.source_assignment_id else exp.source_project_id
            if not project:
                continue
            if project.id not in result:
                result[project.id] = {
                    "hm": defaultdict(float),
                    "ccp": defaultdict(float),
                }
            result[project.id]["hm"][exp.period.month] += exp.cost_hm or 0.0
            result[project.id]["ccp"][exp.period.month] += exp.cost_ccp or 0.0
        return result

    def _group_internal_wage_by_assignment(self, wage_expenses):
        result = {}
        for exp in wage_expenses.filtered("source_assignment_id"):
            assignment = exp.source_assignment_id
            if assignment.id not in result:
                result[assignment.id] = {
                    "hm": defaultdict(float),
                    "ccp": defaultdict(float),
                }
            result[assignment.id]["hm"][exp.period.month] += exp.cost_hm or 0.0
            result[assignment.id]["ccp"][exp.period.month] += exp.cost_ccp or 0.0
        return result

    def _aggregate_internal_expense_bucket_by_month(self, expenses, tokens):
        result = defaultdict(float)
        for expense in expenses:
            if not self._matches_internal_expense_tokens(expense, tokens):
                continue
            result[expense.period.month] += expense.cost_ccp or expense.expense_amount or 0.0
        return result

    def _matches_internal_expense_tokens(self, expense, tokens):
        search_parts = [
            expense.expense_type_config_id.name,
            expense.expense_type_config_id.display_name,
            expense.hr_expense_id.name,
            expense.hr_expense_id.product_id.display_name,
        ]
        haystack = " ".join(part for part in search_parts if part).lower()
        return any(token in haystack for token in tokens)

    def _subtract_monthly_values(self, source_values, subtract_values):
        result = defaultdict(float)
        for month in range(1, 13):
            result[month] = max(0.0, (source_values.get(month, 0.0) - subtract_values.get(month, 0.0)))
        return result

    def _build_report_line(self, report, options, name, monthly_values, figure_type, level, line_id_markup, parent_line_id=None):
        line = {
            "id": report._get_generic_line_id(None, None, markup=line_id_markup, parent_line_id=parent_line_id),
            "name": name,
            "columns": self._build_allocation_columns(report, options, monthly_values, figure_type),
            "level": level,
        }
        if parent_line_id:
            line["parent_id"] = parent_line_id
        return line

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
