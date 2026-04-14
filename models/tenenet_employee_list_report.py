from datetime import date

from odoo import fields, models
from odoo.tools import format_date


class TenenetEmployeeListReportHandler(models.AbstractModel):
    _name = "tenenet.employee.list.report.handler"
    _inherit = ["account.report.custom.handler"]
    _description = "TENENET Zoznam zamestnancov"

    _AVAILABILITY_SELECTION = [
        ("free", "Voľný"),
        ("partial", "Čiastočne alokovaný"),
        ("full", "Plne alokovaný"),
        ("overbooked", "Preťažený"),
    ]
    _GROUPING_SELECTION = [
        ("none", "Bez zoskupenia"),
        ("profession", "Podľa profesie"),
        ("availability", "Podľa vyťaženosti"),
    ]
    _FLOAT_COLUMNS = {"work_hours", "utilization_percentage"}
    _STRING_COLUMNS = {
        "employee_name",
        "tenenet_number",
        "title_academic",
        "last_name",
        "first_name",
        "position",
        "all_job_names",
        "main_site_name",
        "secondary_site_names",
        "study_field",
        "work_phone",
        "manager_name",
        "project_names",
        "program_names",
    }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        custom_display_config = options["custom_display_config"]
        custom_display_config["css_custom_class"] = (
            custom_display_config.get("css_custom_class", "") + " tenenet_employee_list_report tenenet_utilization_report"
        ).strip()
        custom_display_config.setdefault("components", {})["AccountReportFilters"] = (
            "TenenetEmployeeListReportFilters"
        )

        period = self._get_selected_month_start(options)
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

        language_skill_type = self._get_language_skill_type()
        selected_jobs = self._get_selected_jobs(previous_options)
        selected_main_sites = self._get_selected_main_sites(previous_options)
        selected_projects = self._get_selected_projects(previous_options)
        selected_programs = self._get_selected_programs(previous_options)
        selected_language_skills = self._get_selected_language_skills(previous_options, language_skill_type)
        selected_availability_states = self._get_selected_availability_states(previous_options)
        grouping_mode = self._get_grouping_mode(previous_options)

        options["job_ids"] = selected_jobs.ids
        options["selected_job_names"] = selected_jobs.mapped("display_name")
        options["main_site_ids"] = selected_main_sites.ids
        options["selected_main_site_names"] = selected_main_sites.mapped("display_name")
        options["project_ids"] = selected_projects.ids
        options["selected_project_names"] = selected_projects.mapped("display_name")
        options["program_ids"] = selected_programs.ids
        options["selected_program_names"] = selected_programs.mapped("display_name")
        options["language_skill_ids"] = selected_language_skills.ids
        options["selected_language_names"] = selected_language_skills.mapped("name")
        options["language_skill_domain"] = (
            [["skill_type_id", "=", language_skill_type.id]]
            if language_skill_type
            else [["id", "=", 0]]
        )
        options["availability_filter_selection"] = [
            {"id": key, "name": label, "selected": key in selected_availability_states}
            for key, label in self._AVAILABILITY_SELECTION
        ]
        options["grouping_mode"] = grouping_mode
        options["grouping_mode_selection"] = [
            {"id": key, "name": label, "selected": key == grouping_mode}
            for key, label in self._GROUPING_SELECTION
        ]

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        period = self._get_selected_month_start(options)
        utilization_by_employee = self._get_utilization_by_employee(period)
        employees = self._get_employee_records(
            options,
            search_term=options.get("filter_search_bar"),
        )
        grouping_mode = options.get("grouping_mode", "none")
        if grouping_mode == "profession":
            return self._get_grouped_lines(report, options, employees, grouping_mode, utilization_by_employee)
        if grouping_mode == "availability":
            return self._get_grouped_lines(report, options, employees, grouping_mode, utilization_by_employee)
        return [
            (0, self._get_report_line(report, options, employee, utilization_by_employee))
            for employee in employees
        ]

    def _get_employee_records(self, options, search_term=None):
        employees = self.env["hr.employee"].search(
            [],
            order="main_site_id, tenenet_number, last_name, first_name, name",
        )
        selected_period = self._get_selected_month_start(options)
        language_skill_type = self._get_language_skill_type()
        selected_job_ids = set(options.get("job_ids") or [])
        selected_main_site_ids = set(options.get("main_site_ids") or [])
        selected_project_ids = set(options.get("project_ids") or [])
        selected_program_ids = set(options.get("program_ids") or [])
        selected_language_skill_ids = set(options.get("language_skill_ids") or [])
        selected_availability_states = {
            item["id"]
            for item in options.get("availability_filter_selection", [])
            if item.get("selected")
        }

        if selected_job_ids:
            employees = employees.filtered(lambda rec: rec.job_id.id in selected_job_ids)
            employees |= self.env["hr.employee"].search([
                ("id", "not in", employees.ids),
                ("additional_job_ids", "in", list(selected_job_ids)),
            ])
            employees = employees.sorted(
                key=lambda rec: (
                    rec.main_site_id.display_name or "",
                    rec.tenenet_number or 0,
                    rec.last_name or "",
                    rec.first_name or "",
                    rec.name or "",
                )
            )
        if selected_main_site_ids:
            employees = employees.filtered(lambda rec: rec.main_site_id.id in selected_main_site_ids)
        if selected_project_ids:
            employees = employees.filtered(
                lambda rec: bool(
                    self._get_assignments_for_employee_month(rec, selected_period).filtered(
                        lambda assignment: assignment.project_id.id in selected_project_ids
                    )
                )
            )
        if selected_program_ids:
            employees = employees.filtered(
                lambda rec: bool(
                    self._get_assignments_for_employee_month(rec, selected_period).filtered(
                        lambda assignment: (
                            (assignment.program_id or assignment.project_id._get_effective_reporting_program()).id
                            in selected_program_ids
                        )
                    )
                )
            )
        if selected_availability_states:
            employees = employees.filtered(
                lambda rec: rec.tenenet_availability_state in selected_availability_states
            )
        if selected_language_skill_ids:
            employees = employees.filtered(
                lambda rec: bool(
                    self._get_current_language_skills(rec, language_skill_type).filtered(
                        lambda skill_line: skill_line.skill_id.id in selected_language_skill_ids
                    )
                )
            )
        if search_term:
            lowered_search_term = search_term.lower()
            employees = employees.filtered(
                lambda rec: lowered_search_term in (rec.name or "").lower()
                or lowered_search_term in (rec.title_academic or "").lower()
                or lowered_search_term in (rec.first_name or "").lower()
                or lowered_search_term in (rec.last_name or "").lower()
                or lowered_search_term in (rec.position or "").lower()
                or lowered_search_term in (rec.job_id.name or "").lower()
                or lowered_search_term in (rec.all_job_names or "").lower()
                or lowered_search_term in (rec.all_site_names or "").lower()
                or lowered_search_term in (rec.study_field or "").lower()
                or lowered_search_term in (rec.work_phone or "").lower()
                or lowered_search_term in (rec.parent_id.name or "").lower()
            )
        return employees

    def _get_grouped_lines(self, report, options, employees, grouping_mode, utilization_by_employee):
        lines = []
        for section_key, section_label, section_employees in self._group_employees(employees, grouping_mode):
            lines.append((0, self._get_section_line(report, options, grouping_mode, section_key, section_label)))
            lines.extend(
                (0, self._get_report_line(report, options, employee, utilization_by_employee, level=2))
                for employee in section_employees
            )
        return lines

    def _group_employees(self, employees, grouping_mode):
        grouped = []
        if grouping_mode == "profession":
            sections = {}
            for employee in employees:
                group_key = employee.job_id.id or 0
                sections.setdefault(group_key, self.env["hr.employee"])
                sections[group_key] |= employee
            for group_key, section_employees in sorted(
                sections.items(),
                key=lambda item: self._get_profession_group_label(item[1][:1]).lower(),
            ):
                grouped.append((
                    group_key,
                    self._get_profession_group_label(section_employees[:1]),
                    section_employees,
                ))
            return grouped

        availability_map = {key: [] for key, _label in self._AVAILABILITY_SELECTION}
        other_employees = []
        for employee in employees:
            state = employee.tenenet_availability_state
            if state in availability_map:
                availability_map[state].append(employee.id)
            else:
                other_employees.append(employee.id)

        for state, label in self._AVAILABILITY_SELECTION:
            employee_ids = availability_map[state]
            if employee_ids:
                grouped.append((
                    state,
                    label,
                    self.env["hr.employee"].browse(employee_ids),
                ))
        if other_employees:
            grouped.append((
                "other",
                "Nezaradené",
                self.env["hr.employee"].browse(other_employees),
            ))
        return grouped

    def _get_profession_group_label(self, employee):
        employee.ensure_one()
        return employee.job_id.name or employee.position or "Bez profesie"

    def _get_section_line(self, report, options, grouping_mode, section_key, section_label):
        return {
            "id": report._get_generic_line_id(
                None,
                None,
                markup=f"tenenet_employee_list_{grouping_mode}_{section_key}",
            ),
            "name": section_label,
            "columns": self._build_empty_columns(report, options),
            "level": 1,
            "unfoldable": False,
        }

    def _get_report_line(self, report, options, employee, utilization_by_employee, level=2):
        columns = []
        for column in options["columns"]:
            label = column["expression_label"]
            columns.append(
                report._build_column_dict(
                    self._get_column_value(employee, label, utilization_by_employee, options),
                    column,
                    options=options,
                    digits=2,
                )
            )

        return {
            "id": report._get_generic_line_id("hr.employee", employee.id, markup="tenenet_employee_list"),
            "name": "",
            "columns": columns,
            "level": level,
        }

    def _get_column_value(self, employee, label, utilization_by_employee, options):
        if label in {"project_names", "program_names"}:
            assignment_context = self._get_employee_assignment_context(
                employee,
                self._get_selected_month_start(options),
            )
            return assignment_context[label]
        if label == "main_site_name":
            return employee.main_site_id.display_name or ""
        if label == "secondary_site_names":
            secondary_sites = employee._get_site_sequence()
            return ", ".join(site.display_name for site in secondary_sites[1:])
        if label == "employee_name":
            return employee.name or ""
        if label == "manager_name":
            return employee.parent_id.name or ""
        if label == "tenenet_number":
            return str(employee.tenenet_number) if employee.tenenet_number else ""
        if label == "utilization_percentage":
            utilization = utilization_by_employee.get(employee.id)
            return utilization.utilization_percentage if utilization else 0.0
        if label == "all_job_names":
            return employee.all_job_names or ""
        if label in self._STRING_COLUMNS:
            return employee[label] or ""
        if label in self._FLOAT_COLUMNS:
            return employee[label] or 0.0
        return ""

    def _get_employee_assignment_context(self, employee, period):
        employee.ensure_one()
        assignments = self._get_assignments_for_employee_month(employee, period)
        project_names = []
        program_names = []
        for assignment in assignments.sorted(
            key=lambda rec: (
                rec.project_id.display_name or "",
                rec.program_id.display_name or rec.project_id.display_name or "",
                rec.id,
            )
        ):
            project = assignment.project_id
            if project.display_name and project.display_name not in project_names:
                project_names.append(project.display_name)
            program = assignment.program_id or project._get_effective_reporting_program()
            if not program:
                continue
            if program.code == "ADMIN_TENENET" and project.project_type == "medzinarodny":
                continue
            if program.display_name and program.display_name not in program_names:
                program_names.append(program.display_name)
        return {
            "project_names": ", ".join(project_names),
            "program_names": ", ".join(program_names),
        }

    def _get_assignments_for_employee_month(self, employee, period):
        employee.ensure_one()
        period_start = fields.Date.to_date(period) if period else fields.Date.context_today(self)
        period_start = date(period_start.year, period_start.month, 1)
        period_end = fields.Date.end_of(period_start, "month")
        return employee.assignment_ids.filtered(
            lambda assignment: assignment.active
            and not assignment.project_id.is_tenenet_internal
            and assignment.project_id.active
            and (
                (not assignment._get_effective_date_range()[0] or assignment._get_effective_date_range()[0] <= period_end)
                and (not assignment._get_effective_date_range()[1] or assignment._get_effective_date_range()[1] >= period_start)
            )
        )

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

    def _get_selected_jobs(self, previous_options):
        job_ids = self._sanitize_ids(previous_options and previous_options.get("job_ids"))
        return self.env["hr.job"].browse(job_ids).exists()

    def _get_selected_main_sites(self, previous_options):
        site_ids = self._sanitize_ids(previous_options and previous_options.get("main_site_ids"))
        return self.env["tenenet.project.site"].with_context(active_test=False).browse(site_ids).exists()

    def _get_selected_projects(self, previous_options):
        project_ids = self._sanitize_ids(previous_options and previous_options.get("project_ids"))
        return self.env["tenenet.project"].with_context(active_test=False).browse(project_ids).exists()

    def _get_selected_programs(self, previous_options):
        program_ids = self._sanitize_ids(previous_options and previous_options.get("program_ids"))
        return self.env["tenenet.program"].with_context(active_test=False).browse(program_ids).exists()

    def _get_selected_month_start(self, options):
        date_to = options.get("date", {}).get("date_to") or fields.Date.context_today(self)
        return self.env["tenenet.utilization"]._normalize_period(date_to)

    def _get_month_offset(self, period):
        period_date = fields.Date.to_date(period)
        today = fields.Date.context_today(self)
        today_month_start = today.replace(day=1)
        return (period_date.year - today_month_start.year) * 12 + period_date.month - today_month_start.month

    def _get_utilization_by_employee(self, period):
        records = self.env["tenenet.utilization"].sudo()._refresh_for_period(period)
        return {record.employee_id.id: record for record in records if record.employee_id}

    def _get_selected_language_skills(self, previous_options, language_skill_type):
        skill_ids = self._sanitize_ids(previous_options and previous_options.get("language_skill_ids"))
        domain = [("id", "in", skill_ids)]
        if language_skill_type:
            domain.append(("skill_type_id", "=", language_skill_type.id))
        else:
            domain.append(("id", "=", 0))
        return self.env["hr.skill"].search(domain)

    def _get_selected_availability_states(self, previous_options):
        selection_items = previous_options and previous_options.get("availability_filter_selection")
        if not selection_items:
            return set()
        valid_states = {key for key, _label in self._AVAILABILITY_SELECTION}
        return {
            item.get("id")
            for item in selection_items
            if item.get("selected") and item.get("id") in valid_states
        }

    def _get_grouping_mode(self, previous_options):
        grouping_mode = previous_options and previous_options.get("grouping_mode")
        if isinstance(grouping_mode, dict):
            grouping_mode = grouping_mode.get("id")
        elif isinstance(grouping_mode, list):
            selected_grouping = next(
                (item for item in grouping_mode if item.get("selected")),
                {},
            )
            grouping_mode = selected_grouping.get("id")
        valid_modes = {key for key, _label in self._GROUPING_SELECTION}
        return grouping_mode if grouping_mode in valid_modes else "none"

    def _sanitize_ids(self, values):
        sanitized = []
        for value in values or []:
            try:
                sanitized.append(int(value))
            except (TypeError, ValueError):
                continue
        return sanitized

    def _get_language_skill_type(self):
        skill_type = self.env.ref("hr_skills.hr_skill_type_lang", raise_if_not_found=False)
        if skill_type:
            return skill_type
        return self.env["hr.skill.type"].search(
            ["|", ("name", "ilike", "language"), ("name", "ilike", "jazyk")],
            limit=1,
        )

    def _get_current_language_skills(self, employee, language_skill_type):
        skill_lines = employee.current_employee_skill_ids
        if language_skill_type:
            skill_lines = skill_lines.filtered(lambda rec: rec.skill_type_id == language_skill_type)
        return skill_lines
