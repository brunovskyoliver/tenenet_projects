from odoo import fields, models


class TenenetProjectSummaryReportHandler(models.AbstractModel):
    _name = "tenenet.project.summary.report.handler"
    _inherit = ["account.report.custom.handler", "tenenet.pl.reporting.support"]
    _description = "TENENET Project Summary Report Handler"

    _PROJECT_SCOPE_SELECTION = [
        ("active_year", "Aktívne v roku"),
        ("all", "Všetky dostupné"),
    ]
    _SEMAPHORE_SELECTION = [
        ("green", "Zelená"),
        ("orange", "Oranžová"),
        ("red", "Červená"),
    ]

    _DATE_COLUMNS = {"contract_date", "date_start", "date_end"}
    _MONETARY_COLUMNS = {
        "project_budget",
        "contractual_total",
        "received_selected_year",
        "received_total",
        "received_diff",
    }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        custom_display_config = options["custom_display_config"]
        custom_display_config["css_custom_class"] = (
            custom_display_config.get("css_custom_class", "") + " tenenet_project_summary_report"
        ).strip()
        custom_display_config.setdefault("components", {})["AccountReportFilters"] = (
            "TenenetProjectSummaryReportFilters"
        )

        selected_year = self._get_selected_year(options)
        self._set_year_options(options, selected_year)

        available_projects = self.env["tenenet.project"].with_context(active_test=False).get_report_accessible_projects()
        available_programs = (
            available_projects.mapped("reporting_program_id")
            | available_projects.mapped("ui_program_ids")
            | available_projects.mapped("program_ids")
        ).filtered(lambda program: not program.is_tenenet_internal)
        available_donors = available_projects.mapped("donor_id")

        selected_programs = self._get_selected_records(
            "tenenet.program",
            previous_options and previous_options.get("program_ids"),
            available_programs,
        )
        selected_donors = self._get_selected_records(
            "tenenet.donor",
            previous_options and previous_options.get("donor_ids"),
            available_donors,
        )
        project_type = self._get_selected_value(
            previous_options and previous_options.get("project_type"),
            {key for key, _label in self.env["tenenet.project"].PROJECT_TYPE_SELECTION},
            default=False,
        )
        semaphore = self._get_selected_value(
            previous_options and previous_options.get("semaphore"),
            {key for key, _label in self._SEMAPHORE_SELECTION},
            default=False,
        )
        project_scope = self._get_selected_value(
            previous_options and previous_options.get("project_scope"),
            {key for key, _label in self._PROJECT_SCOPE_SELECTION},
            default="active_year",
        )

        options["program_ids"] = selected_programs.ids
        options["selected_program_names"] = selected_programs.mapped("display_name")
        options["donor_ids"] = selected_donors.ids
        options["selected_donor_names"] = selected_donors.mapped("display_name")
        options["project_type"] = project_type
        options["semaphore"] = semaphore
        options["project_scope"] = project_scope
        options["available_program_domain"] = [("id", "in", available_programs.ids or [0])]
        options["available_donor_domain"] = [("id", "in", available_donors.ids or [0])]
        options["project_type_selection"] = self._build_selection_options(
            self.env["tenenet.project"].PROJECT_TYPE_SELECTION,
            project_type,
            empty_label="Všetky typy",
        )
        options["semaphore_selection"] = self._build_selection_options(
            self._SEMAPHORE_SELECTION,
            semaphore,
            empty_label="Všetky",
        )
        options["project_scope_selection"] = [
            {"id": key, "name": label, "selected": key == project_scope}
            for key, label in self._PROJECT_SCOPE_SELECTION
        ]

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        projects = self._get_filtered_projects(options, search_term=options.get("filter_search_bar"))
        aggregates = self._get_project_aggregates(projects, self._get_selected_year(options))
        return [
            (0, self._build_project_line(report, options, project, aggregates.get(project.id, {})))
            for project in projects
        ]

    def _get_filtered_projects(self, options, search_term=None):
        selected_year = self._get_selected_year(options)
        project_scope = options.get("project_scope") or "active_year"
        selected_program_ids = set(options.get("program_ids") or [])
        selected_donor_ids = set(options.get("donor_ids") or [])
        project_type = options.get("project_type")
        semaphore = options.get("semaphore")

        projects = self.env["tenenet.project"].with_context(active_test=False).get_report_accessible_projects()
        if project_scope == "active_year":
            projects = projects.filtered(
                lambda project: bool(project.active_year_from)
                and bool(project.active_year_to)
                and project.active_year_from <= selected_year <= project.active_year_to
            )
        if project_type:
            projects = projects.filtered(lambda project: project.project_type == project_type)
        if semaphore:
            projects = projects.filtered(lambda project: project.semaphore == semaphore)
        if selected_donor_ids:
            projects = projects.filtered(lambda project: project.donor_id.id in selected_donor_ids)
        if selected_program_ids:
            projects = projects.filtered(
                lambda project: bool(
                    selected_program_ids.intersection(
                        (
                            project.reporting_program_id
                            | project.ui_program_ids
                            | project.program_ids
                        ).ids
                    )
                )
            )
        if search_term:
            lowered_search_term = search_term.lower()
            projects = projects.filtered(
                lambda project: lowered_search_term in (project.name or "").lower()
                or lowered_search_term in (project.contract_number or "").lower()
                or lowered_search_term in (project.donor_id.display_name or "").lower()
                or lowered_search_term in (project.reporting_program_id.display_name or "").lower()
                or lowered_search_term in (project.recipient_partner_id.display_name or "").lower()
                or lowered_search_term in (project.project_manager_id.name or "").lower()
                or lowered_search_term in (project.odborny_garant_id.name or "").lower()
            )
        return projects.sorted(lambda project: (project.name or project.display_name or "").lower())

    def _get_project_aggregates(self, projects, selected_year):
        aggregates = {
            project.id: {
                "selected_year_budget": 0.0,
                "all_budget": 0.0,
                "selected_year_received": 0.0,
                "received_total": 0.0,
            }
            for project in projects
        }
        if not projects:
            return aggregates

        for line in projects.mapped("budget_line_ids"):
            bucket = aggregates.get(line.project_id.id)
            if not bucket:
                continue
            bucket["all_budget"] += line.amount or 0.0
            if line.year == selected_year:
                bucket["selected_year_budget"] += line.amount or 0.0

        for receipt in projects.mapped("receipt_line_ids"):
            bucket = aggregates.get(receipt.project_id.id)
            if not bucket:
                continue
            bucket["received_total"] += receipt.amount or 0.0
            if receipt.year == selected_year:
                bucket["selected_year_received"] += receipt.amount or 0.0

        return aggregates

    def _build_project_line(self, report, options, project, aggregate):
        return {
            "id": report._get_generic_line_id("tenenet.project", project.id, markup="project_summary"),
            "name": "",
            "columns": self._build_columns(report, options, self._get_project_values(project, options, aggregate)),
            "level": 2,
        }

    def _get_project_values(self, project, options, aggregate):
        selected_year = self._get_selected_year(options)
        project_budget = aggregate.get("selected_year_budget", 0.0)
        if options.get("project_scope") == "all":
            project_budget = aggregate.get("all_budget", 0.0)
        contractual_total = aggregate.get("all_budget", 0.0) or project_budget
        received_total = aggregate.get("received_total", 0.0)
        return {
            "year_label": self._get_year_label(project, options, selected_year),
            "semaphore_label": self._get_selection_label(project, "semaphore"),
            "project_name": project.name or "",
            "duration_label": f"{project.duration}M" if project.duration else "",
            "contract_number": project.contract_number or "",
            "recipient": project.recipient_partner_id.display_name or "",
            "project_type_label": self._get_selection_label(project, "project_type"),
            "donor": project.donor_id.display_name or "",
            "program": self._get_project_program_label(project),
            "partners": project.partner_id.display_name or "",
            "contract_date": project.date_contract,
            "project_staff": self._get_project_staff(project),
            "sustainability_note": self._truncate_text(project.description_preview or project.description, 160),
            "portal": project.portal or "",
            "project_budget": project_budget,
            "settlement_note": self._get_settlement_note(project, selected_year),
            "contractual_total": contractual_total,
            "date_start": project.date_start,
            "date_end": project.date_end,
            "received_selected_year": aggregate.get("selected_year_received", 0.0),
            "received_total": received_total,
            "received_diff": received_total - project_budget,
            "odborny_garant": project.odborny_garant_id.name or "",
            "project_manager": project.project_manager_id.name or "",
            "donor_contact": project.donor_contact or "",
            "partner_contact": project.partner_contact or "",
        }

    def _build_columns(self, report, options, values):
        columns = []
        for column in options["columns"]:
            expression_label = column["expression_label"]
            value = values.get(expression_label, "")
            figure_type = column["figure_type"]
            if expression_label in self._DATE_COLUMNS:
                figure_type = "date"
            elif expression_label in self._MONETARY_COLUMNS:
                figure_type = "monetary"
            else:
                figure_type = "string"
            columns.append(
                report._build_column_dict(
                    value,
                    {**column, "figure_type": figure_type},
                    options=options,
                    currency=self.env.company.currency_id if figure_type == "monetary" else False,
                    digits=2,
                )
            )
        return columns

    def _get_year_label(self, project, options, selected_year):
        if options.get("project_scope") != "all":
            return str(selected_year)
        if project.active_year_from and project.active_year_to:
            if project.active_year_from == project.active_year_to:
                return str(project.active_year_from)
            return f"{project.active_year_from}-{project.active_year_to}"
        return ""

    def _get_project_program_label(self, project):
        if project.reporting_program_id:
            return project.reporting_program_id.display_name or ""
        programs = project.ui_program_ids or project.program_ids
        return ", ".join(programs.mapped("display_name"))

    def _get_project_staff(self, project):
        staff = []
        if project.odborny_garant_id:
            staff.append(project.odborny_garant_id.name)
        if project.project_manager_id and project.project_manager_id != project.odborny_garant_id:
            staff.append(project.project_manager_id.name)
        return ", ".join(staff)

    def _get_settlement_note(self, project, selected_year):
        today = fields.Date.context_today(self)
        milestones = project.milestone_ids.filtered(lambda milestone: milestone.date and milestone.date >= today)
        if not milestones:
            year_start = fields.Date.to_date(f"{selected_year}-01-01")
            year_end = fields.Date.to_date(f"{selected_year}-12-31")
            milestones = project.milestone_ids.filtered(
                lambda milestone: milestone.date and year_start <= milestone.date <= year_end
            )
        milestone = milestones.sorted(lambda rec: (rec.date, rec.sequence, rec.id))[:1]
        if not milestone:
            return ""
        parts = [milestone.name]
        if milestone.date:
            parts.append(fields.Date.to_string(milestone.date))
        if milestone.note:
            parts.append(self._truncate_text(milestone.note, 120))
        return " - ".join(parts)

    def _get_selection_label(self, record, field_name):
        value = record[field_name]
        if not value:
            return ""
        if field_name == "semaphore":
            return dict(self._SEMAPHORE_SELECTION).get(value, value)
        return dict(record._fields[field_name].selection).get(value, value)

    def _truncate_text(self, value, limit):
        text = " ".join((value or "").split())
        if len(text) <= limit:
            return text
        return f"{text[:limit - 3].rstrip()}..."

    def _get_selected_records(self, model_name, values, allowed_records):
        ids = self._sanitize_ids(values)
        records = self.env[model_name].with_context(active_test=False).browse(ids).exists()
        return records & allowed_records

    def _get_selected_value(self, value, allowed_values, default=False):
        if isinstance(value, dict):
            value = value.get("id")
        return value if value in allowed_values else default

    def _build_selection_options(self, selection, selected_value, empty_label):
        options = [{"id": False, "name": empty_label, "selected": not selected_value}]
        options.extend(
            {"id": key, "name": label, "selected": key == selected_value}
            for key, label in selection
        )
        return options

    def _sanitize_ids(self, values):
        sanitized = []
        for value in values or []:
            try:
                sanitized.append(int(value))
            except (TypeError, ValueError):
                continue
        return sanitized
