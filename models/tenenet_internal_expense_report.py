from collections import defaultdict
from datetime import date

from odoo import fields, models


class TenenetInternalExpenseReportHandler(models.AbstractModel):
    _name = "tenenet.internal.expense.report.handler"
    _inherit = ["account.report.custom.handler"]
    _description = "TENENET Interné náklady – Ročný report"

    # ------------------------------------------------------------------ #
    #  Options initializer                                                 #
    # ------------------------------------------------------------------ #

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        custom_display_config = options["custom_display_config"]
        custom_display_config["css_custom_class"] = (
            custom_display_config.get("css_custom_class", "") + " tenenet_internal_expense_report"
        ).strip()
        custom_display_config.setdefault("components", {})["AccountReportFilters"] = (
            "TenenetInternalExpenseReportFilters"
        )
        custom_display_config.setdefault("templates", {})["AccountReportLineCell"] = (
            "tenenet_projects.TenenetInternalExpenseReportLineCell"
        )

        selected_year = self._get_selected_year(options)
        self._set_year_options(options, selected_year)

    # ------------------------------------------------------------------ #
    #  Top-level line generator                                            #
    # ------------------------------------------------------------------ #

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        selected_year = self._get_selected_year(options)
        expenses = self._get_year_expenses(selected_year)
        if not expenses:
            return []

        employee_buckets = self._group_by_employee(expenses)
        lines = []
        grand_total_hours = defaultdict(float)
        grand_total_costs = defaultdict(float)

        for bucket in sorted(
            employee_buckets.values(),
            key=lambda b: (b["employee"].name or "").lower(),
        ):
            employee = bucket["employee"]
            total_costs = bucket["total_costs"]

            for m in range(1, 13):
                grand_total_hours[m] += bucket["total_hours"][m]
                grand_total_costs[m] += total_costs[m]

            employee_line_id = report._get_generic_line_id(
                "hr.employee",
                employee.id,
                markup="int_exp_employee",
            )
            lines.append((0, {
                "id": employee_line_id,
                "name": employee.name or "",
                "columns": self._build_columns(report, options, total_costs),
                "level": 1,
                "unfoldable": True,
                "unfolded": bool(
                    options.get("unfold_all")
                    or employee_line_id in (options.get("unfolded_lines") or [])
                ),
                "expand_function": "_report_expand_unfoldable_line_int_exp_employee",
            }))

        lines.append((0, {
            "id": report._get_generic_line_id(None, None, markup="int_exp_grand_total_hours"),
            "name": "Hodiny interných nákladov spolu",
            "columns": self._build_columns(report, options, grand_total_hours),
            "level": 1,
        }))
        lines.append((0, {
            "id": report._get_generic_line_id(None, None, markup="int_exp_grand_total_costs"),
            "name": "Náklady interných výdavkov spolu (€)",
            "columns": self._build_columns(report, options, grand_total_costs),
            "level": 1,
        }))
        return lines

    # ------------------------------------------------------------------ #
    #  Expand handler: employee → projects                                 #
    # ------------------------------------------------------------------ #

    def _report_expand_unfoldable_line_int_exp_employee(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        markup, model, record_id = report._parse_line_id(line_dict_id)[-1]
        if model != "hr.employee":
            return {"lines": []}

        employee = self.env["hr.employee"].browse(record_id).exists()
        if not employee:
            return {"lines": []}

        selected_year = self._get_selected_year(options)
        expenses = self._get_year_expenses_for_employee(employee, selected_year)

        project_rows = self._group_by_project(expenses)
        lines = []
        for seq, (project, _hours, total_costs, cost_rows) in enumerate(project_rows, start=1):
            project_id = project.id if project else 0
            project_name = project.name if project else "(Bez projektu)"
            project_line_id = report._get_generic_line_id(
                "tenenet.project" if project_id else None,
                project_id or None,
                parent_line_id=line_dict_id,
                markup=f"int_exp_project_{employee.id}_{project_id}_{seq}",
            )

            lines.append({
                "id": project_line_id,
                "name": project_name,
                "columns": self._build_columns(report, options, total_costs),
                "level": 2,
                "parent_id": line_dict_id,
                "unfoldable": True,
                "unfolded": bool(
                    options.get("unfold_all")
                    or project_line_id in (options.get("unfolded_lines") or [])
                ),
                "expand_function": "_report_expand_unfoldable_line_int_exp_project",
            })
        return {
            "lines": lines,
            "offset_increment": len(lines),
            "has_more": False,
            "progress": progress,
        }

    def _report_expand_unfoldable_line_int_exp_project(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        markup, model, record_id = report._parse_line_id(line_dict_id)[-1]
        employee_id, project_id = self._extract_project_markup(markup)
        if not employee_id:
            return {"lines": []}

        employee = self.env["hr.employee"].browse(employee_id).exists()
        if not employee:
            return {"lines": []}

        selected_year = self._get_selected_year(options)
        expenses = self._get_year_expenses_for_employee(employee, selected_year)
        project_rows = self._group_by_project(expenses)

        target_row = next(
            (row for row in project_rows if ((row[0].id if row[0] else 0) == project_id)),
            None,
        )
        if not target_row:
            return {"lines": []}

        _project, _hours, _total_costs, cost_rows = target_row
        lines = []
        for detail_seq, (type_name, costs) in enumerate(cost_rows, start=1):
            lines.append({
                "id": report._get_generic_line_id(
                    None,
                    None,
                    parent_line_id=line_dict_id,
                    markup=f"int_exp_project_type_{employee_id}_{project_id}_{detail_seq}",
                ),
                "name": type_name,
                "columns": self._build_columns(report, options, costs),
                "level": 3,
                "parent_id": line_dict_id,
            })
        return {
            "lines": lines,
            "offset_increment": len(lines),
            "has_more": False,
            "progress": progress,
        }

    # ------------------------------------------------------------------ #
    #  Data helpers                                                        #
    # ------------------------------------------------------------------ #

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

    def _get_year_expenses(self, selected_year):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        return self.env["tenenet.internal.expense"].search(
            [("period", ">=", year_start), ("period", "<=", year_end)],
            order="employee_id, period",
        )

    def _get_year_expenses_for_employee(self, employee, selected_year):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        return self.env["tenenet.internal.expense"].search(
            [
                ("employee_id", "=", employee.id),
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ],
            order="period",
        )

    def _group_by_employee(self, expenses):
        buckets = {}
        for exp in expenses:
            emp_id = exp.employee_id.id
            if emp_id not in buckets:
                buckets[emp_id] = {
                    "employee": exp.employee_id,
                    "total_hours": defaultdict(float),
                    "total_costs": defaultdict(float),
                }
            buckets[emp_id]["total_hours"][exp.period.month] += exp.hours or 0.0
            buckets[emp_id]["total_costs"][exp.period.month] += exp.cost_hm or 0.0
        return buckets

    def _get_expense_type_bucket(self, expense):
        if expense.category == "expense" and expense.expense_type_config_id:
            return (f"cfg_{expense.expense_type_config_id.id}", f"Náklady - {expense.expense_type_config_id.display_name}")
        category_labels = dict(self.env["tenenet.internal.expense"]._fields["category"].selection)
        return (f"cat_{expense.category}", category_labels.get(expense.category, expense.category or "Bez typu"))

    def _extract_project_markup(self, markup):
        prefix = "int_exp_project_"
        if not markup or not markup.startswith(prefix):
            return (None, None)
        parts = markup[len(prefix):].split("_")
        if len(parts) < 3:
            return (None, None)
        try:
            return (int(parts[0]), int(parts[1]))
        except (TypeError, ValueError):
            return (None, None)

    def _group_by_project(self, expenses):
        """Return list of (project|None, hours_by_month, total_costs_by_month, [(type_name, costs_by_month)]) sorted by project/type."""
        project_hours = {}
        project_total_costs = {}
        project_type_costs = {}
        project_obj = {}

        for exp in expenses:
            project = exp.source_project_id or (exp.source_assignment_id.project_id if exp.source_assignment_id else None)
            proj_key = project.id if project else 0
            if proj_key not in project_hours:
                project_hours[proj_key] = defaultdict(float)
                project_total_costs[proj_key] = defaultdict(float)
                project_type_costs[proj_key] = {}
                project_obj[proj_key] = project if project else None
            project_hours[proj_key][exp.period.month] += exp.hours or 0.0
            project_total_costs[proj_key][exp.period.month] += exp.cost_hm or 0.0
            type_key, type_name = self._get_expense_type_bucket(exp)
            if type_key not in project_type_costs[proj_key]:
                project_type_costs[proj_key][type_key] = {
                    "type_name": type_name,
                    "costs": defaultdict(float),
                }
            project_type_costs[proj_key][type_key]["costs"][exp.period.month] += exp.cost_hm or 0.0

        rows = []
        for proj_key in project_hours:
            cost_rows = sorted(
                [
                    (values["type_name"], values["costs"])
                    for values in project_type_costs[proj_key].values()
                ],
                key=lambda row: (row[0] or "").lower(),
            )
            rows.append((project_obj[proj_key], project_hours[proj_key], project_total_costs[proj_key], cost_rows))
        return sorted(
            rows,
            key=lambda x: (x[0].name or "").lower() if x[0] else "\xff",
        )

    # ------------------------------------------------------------------ #
    #  Column builder                                                      #
    # ------------------------------------------------------------------ #

    def _build_columns(self, report, options, monthly_values):
        columns = []
        for column in options["columns"]:
            expression_label = column["expression_label"]
            if expression_label == "year_total":
                value = sum(monthly_values.get(m, 0.0) for m in range(1, 13))
            else:
                month_number = int(expression_label.split("_")[1])
                value = monthly_values.get(month_number, 0.0)
            columns.append(
                report._build_column_dict(
                    value,
                    {**column, "figure_type": "float"},
                    options=options,
                    digits=2,
                )
            )
        return columns
