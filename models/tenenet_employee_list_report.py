from odoo import models


class TenenetEmployeeListReportHandler(models.AbstractModel):
    _name = "tenenet.employee.list.report.handler"
    _inherit = ["account.report.custom.handler"]
    _description = "TENENET Zoznam zamestnancov"

    _FLOAT_COLUMNS = {"work_hours"}
    _STRING_COLUMNS = {
        "employee_name",
        "tenenet_number",
        "title_academic",
        "last_name",
        "first_name",
        "position",
        "study_field",
        "manager_name",
    }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        custom_display_config = options["custom_display_config"]
        custom_display_config["css_custom_class"] = (
            custom_display_config.get("css_custom_class", "") + " tenenet_pl_report"
        ).strip()

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        employees = self._get_employee_records(search_term=options.get("filter_search_bar"))
        return [
            (0, self._get_report_line(report, options, employee))
            for employee in employees
        ]

    def _get_employee_records(self, search_term=None):
        employees = self.env["hr.employee"].search([], order="tenenet_number, last_name, first_name, name")
        if search_term:
            lowered_search_term = search_term.lower()
            employees = employees.filtered(
                lambda rec: lowered_search_term in (rec.name or "").lower()
                or lowered_search_term in (rec.title_academic or "").lower()
                or lowered_search_term in (rec.first_name or "").lower()
                or lowered_search_term in (rec.last_name or "").lower()
                or lowered_search_term in (rec.position or "").lower()
                or lowered_search_term in (rec.study_field or "").lower()
                or lowered_search_term in (rec.parent_id.name or "").lower()
            )
        return employees

    def _get_report_line(self, report, options, employee):
        columns = []
        for column in options["columns"]:
            label = column["expression_label"]
            columns.append(
                report._build_column_dict(
                    self._get_column_value(employee, label),
                    column,
                    options=options,
                    digits=2,
                )
            )

        return {
            "id": report._get_generic_line_id("hr.employee", employee.id, markup="tenenet_employee_list"),
            "name": "",
            "columns": columns,
            "level": 2,
        }

    def _get_column_value(self, employee, label):
        if label == "employee_name":
            return employee.name or ""
        if label == "manager_name":
            return employee.parent_id.name or ""
        if label == "tenenet_number":
            return str(employee.tenenet_number) if employee.tenenet_number else ""
        if label in self._STRING_COLUMNS:
            return employee[label] or ""
        if label in self._FLOAT_COLUMNS:
            return employee[label] or 0.0
        return ""
