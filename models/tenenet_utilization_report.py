from collections import defaultdict

from odoo import fields, models
from odoo.tools import format_date


class TenenetUtilizationReportHandler(models.AbstractModel):
    _name = "tenenet.utilization.report.handler"
    _inherit = ["account.report.custom.handler"]
    _description = "TENENET Utilization Report Handler"

    _PROJECT_TYPE_LABELS = {
        "national": "Národný",
        "international": "Medzinárodný",
    }
    _PLACEHOLDER_COLUMNS = {
        "monthly_project_income",
        "project_insurance_income",
    }
    _TIME_FLOAT_COLUMNS = {
        "work_ratio",
        "capacity_hours",
        "leaves_kpi_hours",
        "hours_pp",
        "hours_np",
        "hours_travel",
        "hours_training",
        "hours_ambulance",
        "hours_international",
        "hours_project_total",
        "hours_vacation",
        "hours_doctor",
        "hours_sick",
        "hours_holidays",
        "hours_ballast",
        "hours_non_project_total",
        "hours_diff",
    }
    _PERCENTAGE_COLUMNS = {
        "utilization_percentage",
        "non_project_percentage",
    }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        options["ignore_totals_below_sections"] = True
        custom_display_config = options["custom_display_config"]
        custom_display_config["css_custom_class"] = (
            custom_display_config.get("css_custom_class", "") + " tenenet_utilization_report"
        ).strip()
        custom_display_config.setdefault("components", {})["AccountReportFilters"] = "TenenetUtilizationReportFilters"

        period = self._get_selected_month_start(report, options)
        options["date"]["filter"] = "this_month"
        options["date"]["period_type"] = "month"
        options["date"]["period"] = self._get_month_offset(period)
        options["date"]["date_from"] = fields.Date.to_string(period)
        options["date"]["date_to"] = fields.Date.to_string(fields.Date.end_of(period, "month"))
        month_str = format_date(self.env, options["date"]["date_to"], date_format="MMM yyyy")
        options["date"]["string"] = month_str

        for cg_data in options.get("column_groups", {}).values():
            if isinstance(cg_data, dict):
                cg_data["string"] = month_str

        options["tenenet_filter_warnings"] = (
            previous_options.get("tenenet_filter_warnings", False)
            if previous_options
            else False
        )

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        period = self._get_selected_month_start(report, options)
        utilization_records = self.env["tenenet.utilization"].sudo()._sync_for_period(period)
        utilization_records._compute_from_timesheets()
        utilization_records = self._get_utilization_records(
            period,
            search_term=options.get("filter_search_bar"),
            only_warnings=options.get("tenenet_filter_warnings", False),
        )
        detail_by_employee = self._get_month_assignment_details(period)
        return [
            (0, self._get_employee_line(report, options, utilization, detail_by_employee.get(utilization.employee_id.id)))
            for utilization in utilization_records
        ]

    def _report_expand_unfoldable_line_tenenet_utilization_employee(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        markup, model, record_id = report._parse_line_id(line_dict_id)[-1]
        if model != "hr.employee" or markup != "tenenet_utilization_employee":
            return {"lines": []}

        period = self._get_selected_month_start(report, options)
        employee = self.env["hr.employee"].browse(record_id).exists()
        if not employee:
            return {"lines": []}

        detail = self._get_month_assignment_details(period).get(employee.id) or {}
        project_lines = []
        for project_detail in detail.get("projects", []):
            project = project_detail["project"]
            project_lines.append({
                "id": report._get_generic_line_id(
                    "tenenet.project",
                    project.id,
                    parent_line_id=line_dict_id,
                    markup=f"tenenet_utilization_project_{employee.id}_{project.id}",
                ),
                "name": project.display_name or project.name or "",
                "columns": self._build_columns(report, options, project_detail["metrics"]),
                "level": 3,
                "parent_id": line_dict_id,
            })
        return {
            "lines": project_lines,
            "offset_increment": len(project_lines),
            "has_more": False,
            "progress": progress,
        }

    def _get_selected_month_start(self, report, options):
        date_to = options.get("date", {}).get("date_to") or fields.Date.context_today(self)
        return self.env["tenenet.utilization"]._normalize_period(date_to)

    def _get_month_offset(self, period):
        period_date = fields.Date.to_date(period)
        today = fields.Date.context_today(self)
        today_month_start = today.replace(day=1)
        return (period_date.year - today_month_start.year) * 12 + period_date.month - today_month_start.month

    def _get_utilization_records(self, period, search_term=None, only_warnings=False):
        records = self.env["tenenet.utilization"].search([("period", "=", period)])
        if search_term:
            lowered_search_term = search_term.lower()
            records = records.filtered(
                lambda rec: lowered_search_term in (rec.employee_id.name or "").lower()
                or lowered_search_term in (rec.manager_name or "").lower()
            )
        if only_warnings:
            records = records.filtered(
                lambda rec: rec.utilization_status == "warning" or rec.non_project_status == "warning"
            )
        return records.sorted(
            key=lambda rec: (
                (rec.manager_name or "").lower(),
                (rec.employee_id.name or "").lower(),
                rec.employee_id.id,
            )
        )

    def _get_month_assignment_details(self, period):
        utilization_records = self.env["tenenet.utilization"].sudo()._sync_for_period(period)
        utilization_records._compute_from_timesheets()
        utilization_by_employee = {
            utilization.employee_id.id: utilization
            for utilization in utilization_records
            if utilization.employee_id
        }
        assignments = self.env["tenenet.project.assignment"].with_context(active_test=False).search(
            [
                ("project_id.is_tenenet_internal", "=", False),
            ],
            order="employee_id, project_id, date_start, id",
        )
        timesheets = self.env["tenenet.project.timesheet"].with_context(active_test=False).search(
            [
                ("period", "=", period),
                ("project_id.is_tenenet_internal", "=", False),
            ]
        )
        timesheets_by_assignment = {
            timesheet.assignment_id.id: timesheet
            for timesheet in timesheets
            if timesheet.assignment_id
        }
        details_by_employee = {}
        for assignment in assignments:
            employee = assignment.employee_id
            project = assignment.project_id
            if not assignment or not employee or not project:
                continue
            if not assignment._is_period_in_scope(period):
                continue
            timesheet = timesheets_by_assignment.get(assignment.id)
            utilization = utilization_by_employee.get(employee.id)

            employee_detail = details_by_employee.setdefault(employee.id, {
                "employee": employee,
                "manager_name": employee.parent_id.name or "",
                "projects": {},
                "type_counts": defaultdict(int),
            })
            project_detail = employee_detail["projects"].setdefault(project.id, {
                "project": project,
                "assignments": [],
                "type_key": self._get_project_type_key(project),
            })

            metrics = self._get_assignment_metrics(employee, assignment, timesheet, utilization=utilization)
            project_detail["assignments"].append({
                "assignment": assignment,
                "timesheet": timesheet,
                "metrics": metrics,
            })
            employee_detail["type_counts"][project_detail["type_key"]] += 1

        for employee_detail in details_by_employee.values():
            project_rows = []
            for project_detail in employee_detail["projects"].values():
                project_detail["assignments"].sort(
                    key=lambda row: (
                        row["assignment"].date_start or fields.Date.today(),
                        row["assignment"].id,
                    )
                )
                project_detail["metrics"] = self._aggregate_metrics(
                    [row["metrics"] for row in project_detail["assignments"]],
                    manager_name=employee_detail["manager_name"],
                    project_type=self._PROJECT_TYPE_LABELS[project_detail["type_key"]],
                )
                project_rows.append(project_detail)
            employee_detail["projects"] = sorted(
                project_rows,
                key=lambda row: (row["project"].name or "").lower(),
            )
        return details_by_employee

    def _get_employee_line(self, report, options, utilization, detail):
        type_counts = detail.get("type_counts", {}) if detail else {}
        values = self._get_employee_values(utilization, type_counts)
        employee_line_id = report._get_generic_line_id(
            "hr.employee",
            utilization.employee_id.id,
            markup="tenenet_utilization_employee",
        )
        return {
            "id": employee_line_id,
            "name": utilization.employee_id.name or "",
            "columns": self._build_columns(report, options, values),
            "level": 2,
            "unfoldable": bool(detail and detail.get("projects")),
            "unfolded": bool(
                options.get("unfold_all")
                or employee_line_id in (options.get("unfolded_lines") or [])
            ),
            "expand_function": "_report_expand_unfoldable_line_tenenet_utilization_employee",
        }

    def _get_employee_values(self, utilization, type_counts):
        return {
            "manager_name": utilization.manager_name or "",
            "project_type": self._format_employee_project_type(type_counts),
            "monthly_project_income": 0.0,
            "project_insurance_income": 0.0,
            "work_ratio": utilization.work_ratio or 0.0,
            "capacity_hours": utilization.capacity_hours or 0.0,
            "leaves_kpi_hours": utilization.leaves_kpi_hours or 0.0,
            "hours_pp": utilization.hours_pp or 0.0,
            "hours_np": utilization.hours_np or 0.0,
            "hours_travel": utilization.hours_travel or 0.0,
            "hours_training": utilization.hours_training or 0.0,
            "hours_ambulance": utilization.hours_ambulance or 0.0,
            "hours_international": utilization.hours_international or 0.0,
            "hours_project_total": utilization.hours_project_total or 0.0,
            "hours_vacation": utilization.hours_vacation or 0.0,
            "hours_doctor": utilization.hours_doctor or 0.0,
            "hours_sick": utilization.hours_sick or 0.0,
            "hours_holidays": utilization.hours_holidays or 0.0,
            "hours_ballast": utilization.hours_ballast or 0.0,
            "hours_non_project_total": utilization.hours_non_project_total or 0.0,
            "utilization_percentage": utilization.utilization_percentage or 0.0,
            "utilization_status": utilization.utilization_status,
            "non_project_percentage": utilization.non_project_percentage or 0.0,
            "non_project_status": utilization.non_project_status,
            "hours_diff": utilization.hours_diff or 0.0,
        }

    def _get_assignment_metrics(self, employee, assignment, timesheet, utilization=None):
        allocation_ratio = assignment.allocation_ratio or 0.0
        capacity_hours = self._get_assignment_capacity_hours(employee, allocation_ratio, utilization=utilization)
        values = {
            "manager_name": employee.parent_id.name or "",
            "project_type": self._PROJECT_TYPE_LABELS[self._get_project_type_key(assignment.project_id)],
            "monthly_project_income": 0.0,
            "project_insurance_income": 0.0,
            "work_ratio": allocation_ratio,
            "capacity_hours": capacity_hours,
            "hours_pp": timesheet.hours_pp if timesheet else 0.0,
            "hours_np": timesheet.hours_np if timesheet else 0.0,
            "hours_travel": timesheet.hours_travel if timesheet else 0.0,
            "hours_training": timesheet.hours_training if timesheet else 0.0,
            "hours_ambulance": timesheet.hours_ambulance if timesheet else 0.0,
            "hours_international": timesheet.hours_international if timesheet else 0.0,
            "hours_project_total": timesheet.hours_project_total if timesheet else 0.0,
            "hours_vacation": timesheet.hours_vacation if timesheet else 0.0,
            "hours_doctor": timesheet.hours_doctor if timesheet else 0.0,
            "hours_sick": timesheet.hours_sick if timesheet else 0.0,
            "hours_holidays": timesheet.hours_holidays if timesheet else 0.0,
        }
        values["leaves_kpi_hours"] = (
            values["hours_vacation"] + values["hours_doctor"] + values["hours_sick"]
        )
        values["hours_ballast"] = (
            values["hours_np"]
            + values["hours_travel"]
            + values["hours_training"]
            + values["hours_vacation"]
            + values["hours_doctor"]
            + values["hours_sick"]
        )
        values["hours_non_project_total"] = values["hours_ballast"]
        available_hours = capacity_hours - values["leaves_kpi_hours"]
        utilization_rate = (values["hours_pp"] / available_hours) if available_hours > 0 else 0.0
        non_project_rate = (values["hours_ballast"] / capacity_hours) if capacity_hours > 0 else 0.0
        values["utilization_percentage"] = utilization_rate * 100.0
        values["utilization_status"] = "ok" if available_hours > 0 and utilization_rate >= 0.8 else "warning"
        values["non_project_percentage"] = non_project_rate * 100.0
        values["non_project_status"] = "ok" if capacity_hours > 0 and non_project_rate <= 0.25 else "warning"
        values["hours_diff"] = (
            values["hours_project_total"]
            + values["hours_vacation"]
            + values["hours_doctor"]
            + values["hours_sick"]
            + values["hours_holidays"]
            - capacity_hours
        )
        return values

    def _get_assignment_capacity_hours(self, employee, assignment_allocation_ratio, utilization=None):
        base_capacity_hours = (
            utilization.capacity_hours
            if utilization and utilization.capacity_hours is not None
            else employee.monthly_capacity_hours or 0.0
        )
        return base_capacity_hours * (assignment_allocation_ratio or 0.0) / 100.0

    def _aggregate_metrics(self, metrics_list, manager_name="", project_type=""):
        aggregate = {
            "manager_name": manager_name or "",
            "project_type": project_type or "",
            "monthly_project_income": 0.0,
            "project_insurance_income": 0.0,
            "utilization_status": "warning",
            "non_project_status": "warning",
        }
        sum_labels = self._TIME_FLOAT_COLUMNS | self._PERCENTAGE_COLUMNS | self._PLACEHOLDER_COLUMNS
        for label in sum_labels:
            aggregate[label] = sum(metric.get(label, 0.0) for metric in metrics_list)

        available_hours = aggregate["capacity_hours"] - aggregate["leaves_kpi_hours"]
        utilization_rate = (aggregate["hours_pp"] / available_hours) if available_hours > 0 else 0.0
        non_project_rate = (
            (aggregate["hours_ballast"] / aggregate["capacity_hours"])
            if aggregate["capacity_hours"] > 0
            else 0.0
        )
        aggregate["utilization_percentage"] = utilization_rate * 100.0
        aggregate["utilization_status"] = "ok" if available_hours > 0 and utilization_rate >= 0.8 else "warning"
        aggregate["non_project_percentage"] = non_project_rate * 100.0
        aggregate["non_project_status"] = (
            "ok" if aggregate["capacity_hours"] > 0 and non_project_rate <= 0.25 else "warning"
        )
        return aggregate

    def _build_columns(self, report, options, values):
        columns = []
        for column in options["columns"]:
            label = column["expression_label"]
            columns.append(
                report._build_column_dict(
                    self._get_column_value(values, label),
                    column,
                    options=options,
                    digits=2,
                )
            )
        return columns

    def _get_column_value(self, values, label):
        return values.get(label, "" if label in {"manager_name", "project_type", "utilization_status", "non_project_status"} else 0.0)

    def _get_project_type_key(self, project):
        donor_type = project.donor_id.donor_type if project and project.donor_id else False
        if donor_type == "international":
            return "international"
        return "national"

    def _format_employee_project_type(self, type_counts):
        national = int(type_counts.get("national", 0))
        international = int(type_counts.get("international", 0))
        return f"N: {national} / M: {international}"
