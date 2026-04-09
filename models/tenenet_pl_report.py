from collections import defaultdict
import re

from odoo import models


class TenenetPLReportHandler(models.AbstractModel):
    _name = "tenenet.pl.report.handler"
    _inherit = ["account.report.custom.handler", "tenenet.pl.reporting.support"]
    _description = "TENENET P&L Report Handler"
    _DEFAULT_UNFOLDED_MARKUPS = {
        "tenenet_pl_income_section",
        "tenenet_pl_expense_section",
    }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        options["ignore_totals_below_sections"] = True
        custom_display_config = options["custom_display_config"]
        custom_display_config["css_custom_class"] = (
            custom_display_config.get("css_custom_class", "") + " tenenet_pl_report"
        ).strip()
        custom_display_config.setdefault("components", {})["AccountReportFilters"] = "TenenetPLReportFilters"

        selected_program = self._get_selected_program_from_options(previous_options or options)
        options["enable_program_filter"] = True
        options["program_ids"] = [selected_program.id] if selected_program else []
        options["selected_program_name"] = self._get_program_line_name(selected_program) if selected_program else "Program"

        selected_year = self._get_selected_year(options)
        self._set_year_options(options, selected_year)
        self.env["tenenet.pl.line"]._sync_for_year(selected_year)
        self.env["tenenet.pl.program.override"].sync_year_rows(selected_year)

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        program = self._get_selected_program_from_options(options)
        if not program:
            return []

        lines = [
            self._build_unfoldable_section_line(
                report,
                options,
                "Príjmy/výnosy",
                "tenenet_pl_income_section",
                "_report_expand_unfoldable_line_tenenet_pl_income_section",
            ),
            self._build_unfoldable_section_line(
                report,
                options,
                "Náklady",
                "tenenet_pl_expense_section",
                "_report_expand_unfoldable_line_tenenet_pl_expense_section",
            ),
        ]
        return [(0, line) for line in lines]

    def _report_expand_unfoldable_line_tenenet_pl_income_section(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        program = self._get_selected_program_from_options(options)
        values = self._get_selected_program_report_values(options)
        if self._is_admin_tenenet_program(program):
            lines = [
                self._build_unfoldable_section_line(
                    report,
                    options,
                    "Paušály",
                    "tenenet_pl_admin_pausal_section",
                    "_report_expand_unfoldable_line_tenenet_pl_admin_pausal_section",
                    level=2,
                    parent_line_id=line_dict_id,
                    unfoldable=bool(values["project_rows"]),
                    monthly_values=values["projects_total"],
                ),
                self._build_value_line(
                    report,
                    options,
                    "Prevádzkové príjmy",
                    values["operating_income"],
                    "tenenet_pl_operating_income",
                    level=2,
                    parent_line_id=line_dict_id,
                ),
                self._build_value_line(
                    report,
                    options,
                    "Príjmy spolu",
                    values["income_total"],
                    "tenenet_pl_income_total",
                    level=2,
                    parent_line_id=line_dict_id,
                ),
            ]
            return self._build_expand_result(lines, progress)

        projects_line = self._build_unfoldable_section_line(
            report,
            options,
            "Projekty",
            "tenenet_pl_projects_section",
            "_report_expand_unfoldable_line_tenenet_pl_projects_section",
            level=2,
            parent_line_id=line_dict_id,
            unfoldable=bool(values["project_rows"]),
            monthly_values=values["projects_total"],
        )
        sales_line = self._build_unfoldable_section_line(
            report,
            options,
            "Tržby",
            "tenenet_pl_sales_section",
            "_report_expand_unfoldable_line_tenenet_pl_sales_section",
            level=2,
            parent_line_id=line_dict_id,
            unfoldable=True,
            monthly_values=values["sales_total"],
        )
        fundraising_line = self._build_unfoldable_section_line(
            report,
            options,
            "Zbierky",
            "tenenet_pl_fundraising_section",
            "_report_expand_unfoldable_line_tenenet_pl_fundraising_section",
            level=2,
            parent_line_id=line_dict_id,
            unfoldable=bool(values["fundraising_rows"]),
            monthly_values=values["fundraising_total"],
        )
        lines = [projects_line]
        if values["budget_labor_income_rows"] or any(values["budget_labor_income_total"].values()):
            lines.append(self._build_unfoldable_section_line(
                report,
                options,
                "Mzdové rozpočty",
                "tenenet_pl_budget_income_labor_section",
                "_report_expand_unfoldable_line_tenenet_pl_budget_income_labor_section",
                level=2,
                parent_line_id=line_dict_id,
                unfoldable=bool(values["budget_labor_income_rows"]),
                monthly_values=values["budget_labor_income_total"],
            ))
        if values["budget_other_income_rows"] or any(values["budget_other_income_total"].values()):
            lines.append(self._build_unfoldable_section_line(
                report,
                options,
                "Iné rozpočty",
                "tenenet_pl_budget_income_other_section",
                "_report_expand_unfoldable_line_tenenet_pl_budget_income_other_section",
                level=2,
                parent_line_id=line_dict_id,
                unfoldable=bool(values["budget_other_income_rows"]),
                monthly_values=values["budget_other_income_total"],
            ))
        lines.extend([
            sales_line,
            fundraising_line,
            self._build_value_line(
                report,
                options,
                "Príjmy spolu",
                values["income_total"],
                "tenenet_pl_income_total",
                level=2,
                parent_line_id=line_dict_id,
            ),
        ])
        return self._build_expand_result(lines, progress)

    def _report_expand_unfoldable_line_tenenet_pl_admin_pausal_section(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        values = self._get_selected_program_report_values(options)
        lines = []
        for row in values["project_rows"]:
            if row.get("detail_rows"):
                lines.append(self._build_unfoldable_section_line(
                    report,
                    options,
                    row["name"],
                    markup=f"tenenet_pl_project_income_{row['project'].id}",
                    expand_function="_report_expand_unfoldable_line_tenenet_pl_project_income_detail",
                    level=3,
                    parent_line_id=line_dict_id,
                    unfoldable=True,
                    monthly_values=row["values"],
                    model="tenenet.project",
                    record_id=row["project"].id,
                ))
            else:
                lines.append(self._build_value_line(
                    report,
                    options,
                    row["name"],
                    row["values"],
                    markup=f"tenenet_pl_project_income_{row['project'].id}",
                    level=3,
                    parent_line_id=line_dict_id,
                    model="tenenet.project",
                    record_id=row["project"].id,
                ))
        return self._build_expand_result(lines, progress)

    def _report_expand_unfoldable_line_tenenet_pl_projects_section(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        values = self._get_selected_program_report_values(options)
        lines = []
        for row in values["project_rows"]:
            if row.get("detail_rows"):
                lines.append(self._build_unfoldable_section_line(
                    report,
                    options,
                    row["name"],
                    markup=f"tenenet_pl_project_income_{row['project'].id}",
                    expand_function="_report_expand_unfoldable_line_tenenet_pl_project_income_detail",
                    level=3,
                    parent_line_id=line_dict_id,
                    unfoldable=True,
                    monthly_values=row["values"],
                    model="tenenet.project",
                    record_id=row["project"].id,
                ))
            else:
                lines.append(self._build_value_line(
                    report,
                    options,
                    row["name"],
                    row["values"],
                    markup=f"tenenet_pl_project_income_{row['project'].id}",
                    level=3,
                    parent_line_id=line_dict_id,
                    model="tenenet.project",
                    record_id=row["project"].id,
                ))
        return self._build_expand_result(lines, progress)

    def _report_expand_unfoldable_line_tenenet_pl_project_income_detail(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        values = self._get_selected_program_report_values(options)
        match = re.search(r"tenenet_pl_project_income_(\d+)", str(line_dict_id))
        if not match:
            return self._build_expand_result([], progress)
        project_id = int(match.group(1))
        project_row = next(
            (row for row in values["project_rows"] if row["project"].id == project_id),
            None,
        )
        detail_rows = project_row.get("detail_rows") if project_row else []
        lines = [
            self._build_value_line(
                report,
                options,
                row["name"],
                row["values"],
                markup=f"tenenet_pl_project_income_detail_{row['budget_line'].id}",
                level=4,
                parent_line_id=line_dict_id,
                model="tenenet.project.budget.line",
                record_id=row["budget_line"].id,
            )
            for row in detail_rows
        ]
        return self._build_expand_result(lines, progress)

    def _expand_budget_income_section(self, line_dict_id, options, progress, row_key):
        report = self.env["account.report"].browse(options["report_id"])
        values = self._get_selected_program_report_values(options)
        rows = values.get(row_key, [])
        lines = [
            self._build_value_line(
                report,
                options,
                row["name"],
                row["values"],
                markup=f"tenenet_pl_budget_income_{row['budget_line'].id}",
                level=3,
                parent_line_id=line_dict_id,
                model="tenenet.project.budget.line",
                record_id=row["budget_line"].id,
            )
            for row in rows
        ]
        return self._build_expand_result(lines, progress)

    def _report_expand_unfoldable_line_tenenet_pl_budget_income_labor_section(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        return self._expand_budget_income_section(line_dict_id, options, progress, "budget_labor_income_rows")

    def _report_expand_unfoldable_line_tenenet_pl_budget_income_other_section(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        return self._expand_budget_income_section(line_dict_id, options, progress, "budget_other_income_rows")

    def _report_expand_unfoldable_line_tenenet_pl_sales_section(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        values = self._get_selected_program_report_values(options)
        lines = [
            self._build_value_line(
                report,
                options,
                "Tržby z registračky",
                values["sales_cash_register"],
                "tenenet_pl_sales_cash_register",
                level=3,
                parent_line_id=line_dict_id,
            ),
            self._build_value_line(
                report,
                options,
                "Tržby z faktúr",
                values["sales_invoice"],
                "tenenet_pl_sales_invoice",
                level=3,
                parent_line_id=line_dict_id,
            ),
            self._build_value_line(
                report,
                options,
                "Tržby - neklasifikované",
                values["sales_legacy_unclassified"],
                "tenenet_pl_sales_legacy_unclassified",
                level=3,
                parent_line_id=line_dict_id,
            ),
        ]
        return self._build_expand_result(lines, progress)

    def _report_expand_unfoldable_line_tenenet_pl_fundraising_section(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        values = self._get_selected_program_report_values(options)
        lines = [
            self._build_value_line(
                report,
                options,
                row["name"],
                row["values"],
                markup=f"tenenet_pl_fundraising_{row['campaign'].id}",
                level=3,
                parent_line_id=line_dict_id,
                model="tenenet.fundraising.campaign",
                record_id=row["campaign"].id,
            )
            for row in values["fundraising_rows"]
        ]
        return self._build_expand_result(lines, progress)

    def _report_expand_unfoldable_line_tenenet_pl_expense_section(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        program = self._get_selected_program_from_options(options)
        values = self._get_selected_program_report_values(options)
        if self._is_admin_tenenet_program(program):
            lines = [
                self._build_unfoldable_section_line(
                    report,
                    options,
                    "Mzdové náklady",
                    "tenenet_pl_admin_labor_cost",
                    "_report_expand_unfoldable_line_tenenet_pl_admin_labor_section",
                    level=2,
                    parent_line_id=line_dict_id,
                    unfoldable=bool(values["labor_project_rows"]),
                    monthly_values=values["labor_cost"],
                ),
                self._build_unfoldable_section_line(
                    report,
                    options,
                    "Náklady bez projektov",
                    "tenenet_pl_admin_non_project_cost",
                    "_report_expand_unfoldable_line_tenenet_pl_admin_non_project_cost",
                    level=2,
                    parent_line_id=line_dict_id,
                    unfoldable=bool(values["labor_non_project_rows"]),
                    monthly_values=values["labor_non_project"],
                ),
                self._build_value_line(
                    report,
                    options,
                    "Mzdové náklady administratívy",
                    values["labor_mgmt"],
                    "tenenet_pl_admin_labor_mgmt",
                    level=2,
                    parent_line_id=line_dict_id,
                ),
                self._build_value_line(
                    report,
                    options,
                    "Prevádzkové náklady",
                    values["operating"],
                    "tenenet_pl_operating",
                    level=2,
                    parent_line_id=line_dict_id,
                ),
                self._build_value_line(
                    report,
                    options,
                    "Výsledok programu",
                    values["final_result"],
                    "tenenet_pl_final_result",
                    level=2,
                    parent_line_id=line_dict_id,
                ),
            ]
            return self._build_expand_result(lines, progress)

        lines = [
            self._build_unfoldable_section_line(
                report,
                options,
                "Mzdové náklady - program",
                "tenenet_pl_labor_cost",
                "_report_expand_unfoldable_line_tenenet_pl_labor_cost",
                level=2,
                parent_line_id=line_dict_id,
                unfoldable=bool(values["labor_project_rows"]),
                monthly_values=values["labor_cost"],
            ),
            self._build_value_line(
                report,
                options,
                "Stravné a iné",
                values["stravne"],
                "tenenet_pl_stravne",
                level=2,
                parent_line_id=line_dict_id,
            ),
            self._build_value_line(
                report,
                options,
                "Pokrytie mzdových nákladov",
                values["labor_coverage"],
                "tenenet_pl_labor_coverage",
                level=2,
                parent_line_id=line_dict_id,
            ),
            self._build_value_line(
                report,
                options,
                "Výsledok po mzdových nákladoch",
                values["pre_admin_result"],
                "tenenet_pl_pre_admin_result",
                level=2,
                parent_line_id=line_dict_id,
            ),
            self._build_value_line(
                report,
                options,
                "Prevádzkové náklady",
                values["operating"],
                "tenenet_pl_operating",
                level=2,
                parent_line_id=line_dict_id,
            ),
            self._build_value_line(
                report,
                options,
                "Výsledok programu",
                values["final_result"],
                "tenenet_pl_final_result",
                level=2,
                parent_line_id=line_dict_id,
            ),
        ]
        if values["admin_cost_detail_rows"] or any(values["admin_tenenet_cost"].values()):
            lines.insert(
                4,
                self._build_unfoldable_section_line(
                    report,
                    options,
                    "Admin TENENET náklady",
                    "tenenet_pl_admin_tenenet_cost",
                    "_report_expand_unfoldable_line_tenenet_pl_admin_tenenet_cost",
                    level=2,
                    parent_line_id=line_dict_id,
                    unfoldable=bool(values["admin_cost_detail_rows"]),
                    monthly_values=values["admin_tenenet_cost"],
                ),
            )
        return self._build_expand_result(lines, progress)

    def _report_expand_unfoldable_line_tenenet_pl_admin_tenenet_cost(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        values = self._get_selected_program_report_values(options)
        lines = [
            self._build_value_line(
                report,
                options,
                row["name"],
                row["values"],
                markup=(
                    "tenenet_pl_admin_cost_manual"
                    if row.get("is_manual")
                    else f"tenenet_pl_admin_cost_{row['employee'].id}"
                ),
                level=3,
                parent_line_id=line_dict_id,
                model=None if row.get("is_manual") else "hr.employee",
                record_id=None if row.get("is_manual") else row["employee"].id,
            )
            for row in values["admin_cost_detail_rows"]
        ]
        return self._build_expand_result(lines, progress)

    def _report_expand_unfoldable_line_tenenet_pl_labor_cost(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        values = self._get_selected_program_report_values(options)
        lines = [
            self._build_value_line(
                report,
                options,
                row["name"],
                row["values"],
                markup=f"tenenet_pl_labor_project_{row['project'].id}",
                level=3,
                parent_line_id=line_dict_id,
                model="tenenet.project",
                record_id=row["project"].id,
            )
            for row in values["labor_project_rows"]
        ]
        return self._build_expand_result(lines, progress)

    def _report_expand_unfoldable_line_tenenet_pl_admin_labor_section(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        values = self._get_selected_program_report_values(options)
        lines = [
            self._build_unfoldable_section_line(
                report,
                options,
                row["name"],
                markup=f"tenenet_pl_admin_labor_project_{row['project'].id}",
                expand_function="_report_expand_unfoldable_line_tenenet_pl_admin_labor_project_detail",
                level=3,
                parent_line_id=line_dict_id,
                unfoldable=bool(row.get("employee_rows")),
                monthly_values=row["values"],
                model="tenenet.project",
                record_id=row["project"].id,
            )
            for row in values["labor_project_rows"]
        ]
        return self._build_expand_result(lines, progress)

    def _report_expand_unfoldable_line_tenenet_pl_admin_labor_project_detail(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        values = self._get_selected_program_report_values(options)
        match = re.search(r"tenenet_pl_admin_labor_project_(\d+)", str(line_dict_id))
        if not match:
            return self._build_expand_result([], progress)
        project_id = int(match.group(1))
        project_row = next(
            (row for row in values["labor_project_rows"] if row["project"].id == project_id),
            None,
        )
        lines = [
            self._build_value_line(
                report,
                options,
                row["name"],
                row["values"],
                markup=f"tenenet_pl_admin_labor_employee_{row['employee'].id}",
                level=4,
                parent_line_id=line_dict_id,
                model="hr.employee",
                record_id=row["employee"].id,
            )
            for row in (project_row or {}).get("employee_rows", [])
        ]
        return self._build_expand_result(lines, progress)

    def _report_expand_unfoldable_line_tenenet_pl_admin_non_project_cost(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        values = self._get_selected_program_report_values(options)
        lines = [
            self._build_value_line(
                report,
                options,
                row["name"],
                row["values"],
                markup=f"tenenet_pl_admin_non_project_employee_{row['employee'].id}",
                level=3,
                parent_line_id=line_dict_id,
                model="hr.employee",
                record_id=row["employee"].id,
            )
            for row in values["labor_non_project_rows"]
        ]
        return self._build_expand_result(lines, progress)

    def _build_expand_result(self, lines, progress):
        return {
            "lines": lines,
            "offset_increment": len(lines),
            "has_more": False,
            "progress": progress,
        }

    def _get_selected_program_report_values(self, options):
        program = self._get_selected_program_from_options(options)
        if not program:
            return {}
        selected_year = self._get_selected_year(options)
        return self._get_program_report_values(program, selected_year)

    def _build_unfoldable_section_line(
        self,
        report,
        options,
        name,
        markup,
        expand_function,
        level=1,
        parent_line_id=None,
        unfoldable=True,
        monthly_values=None,
        model=None,
        record_id=None,
    ):
        if monthly_values is None:
            line = self._build_section_line(report, options, name, markup, level=level, parent_line_id=parent_line_id)
        else:
            line = self._build_value_line(
                report,
                options,
                name,
                monthly_values,
                markup,
                level=level,
                parent_line_id=parent_line_id,
                model=model,
                record_id=record_id,
            )
        line["parent_id"] = parent_line_id
        line["unfoldable"] = unfoldable
        line["unfolded"] = bool(
            unfoldable
            and (
                options.get("unfold_all")
                or line["id"] in (options.get("unfolded_lines") or [])
                or markup in self._DEFAULT_UNFOLDED_MARKUPS
            )
        )
        line["expand_function"] = expand_function if unfoldable else None
        return line

    def _build_section_line(self, report, options, name, markup, level=1, parent_line_id=None):
        return {
            "id": report._get_generic_line_id(None, None, parent_line_id=parent_line_id, markup=markup),
            "name": name,
            "columns": self._build_columns(report, options, defaultdict(float), "string"),
            "level": level,
        }

    def _build_value_line(
        self, report, options, name, monthly_values, markup, level=1, parent_line_id=None, model=None, record_id=None
    ):
        line = {
            "id": report._get_generic_line_id(model, record_id, parent_line_id=parent_line_id, markup=markup),
            "name": name,
            "columns": self._build_columns(report, options, monthly_values, "monetary"),
            "level": level,
        }
        if parent_line_id:
            line["parent_id"] = parent_line_id
        return line

    def _build_columns(self, report, options, monthly_values, figure_type):
        columns = []
        for column in options["columns"]:
            expression_label = column["expression_label"]
            if figure_type == "string":
                value = ""
                column_figure_type = "string"
            elif expression_label == "year_total":
                value = round(sum(monthly_values.get(month_index, 0.0) for month_index in range(1, 13)), 2)
                column_figure_type = figure_type
            else:
                month_number = int(expression_label.split("_")[1])
                value = monthly_values.get(month_number, 0.0)
                column_figure_type = figure_type

            columns.append(
                report._build_column_dict(
                    value,
                    {**column, "figure_type": column_figure_type},
                    options=options,
                    currency=self.env.company.currency_id if column_figure_type == "monetary" else False,
                    digits=2,
                )
            )
        return columns


class TenenetPLSummaryReportHandler(models.AbstractModel):
    _name = "tenenet.pl.summary.report.handler"
    _inherit = ["account.report.custom.handler", "tenenet.pl.reporting.support"]
    _description = "TENENET P&L Summary Report Handler"

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        custom_display_config = options["custom_display_config"]
        custom_display_config["css_custom_class"] = (
            custom_display_config.get("css_custom_class", "") + " tenenet_pl_report"
        ).strip()
        custom_display_config.setdefault("components", {})["AccountReportFilters"] = "TenenetPLReportFilters"
        options["enable_program_filter"] = False

        selected_year = self._get_selected_year(options)
        self._set_year_options(options, selected_year)
        self.env["tenenet.pl.line"]._sync_for_year(selected_year)
        self.env["tenenet.pl.program.override"].sync_year_rows(selected_year)

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        selected_year = self._get_selected_year(options)
        programs = self._get_report_programs()
        if not programs:
            return []

        labor_total = defaultdict(float)
        pre_admin_total = defaultdict(float)
        final_total = defaultdict(float)
        lines = [self._build_section_line(report, options, "Mzdové náklady", "tenenet_pl_summary_labor_header")]
        for program in programs:
            values = self._get_program_report_values(program, selected_year)
            for month in range(1, 13):
                labor_total[month] += values["labor_cost"][month]
                pre_admin_total[month] += values["pre_admin_result"][month]
                final_total[month] += values["final_result"][month]
            lines.append(self._build_value_line(
                report,
                options,
                self._get_program_line_name(program),
                values["labor_cost"],
                markup=f"tenenet_pl_summary_labor_{program.id}",
                level=2,
            ))

        lines.append(self._build_value_line(report, options, "Spolu", labor_total, "tenenet_pl_summary_labor_total"))
        lines.append(self._build_section_line(report, options, "P&L bez admin costs", "tenenet_pl_summary_pre_admin_header"))
        for program in programs:
            values = self._get_program_report_values(program, selected_year)
            lines.append(self._build_value_line(
                report,
                options,
                self._get_program_line_name(program),
                values["pre_admin_result"],
                markup=f"tenenet_pl_summary_pre_admin_{program.id}",
                level=2,
            ))

        lines.append(self._build_value_line(report, options, "Spolu", pre_admin_total, "tenenet_pl_summary_pre_admin_total"))
        lines.append(self._build_section_line(report, options, "P&L total", "tenenet_pl_summary_total_header"))
        for program in programs:
            values = self._get_program_report_values(program, selected_year)
            lines.append(self._build_value_line(
                report,
                options,
                self._get_program_line_name(program),
                values["final_result"],
                markup=f"tenenet_pl_summary_total_{program.id}",
                level=2,
            ))
        lines.append(self._build_value_line(report, options, "Spolu", final_total, "tenenet_pl_summary_total_total"))
        return [(0, line) for line in lines]

    def _build_section_line(self, report, options, name, markup):
        return {
            "id": report._get_generic_line_id(None, None, markup=markup),
            "name": name,
            "columns": self._build_columns(report, options, defaultdict(float), "string"),
            "level": 1,
        }

    def _build_value_line(self, report, options, name, monthly_values, markup, level=1):
        return {
            "id": report._get_generic_line_id(None, None, markup=markup),
            "name": name,
            "columns": self._build_columns(report, options, monthly_values, "monetary"),
            "level": level,
        }

    def _build_columns(self, report, options, monthly_values, figure_type):
        columns = []
        for column in options["columns"]:
            expression_label = column["expression_label"]
            if figure_type == "string":
                value = ""
                column_figure_type = "string"
            elif expression_label == "year_total":
                value = round(sum(monthly_values.get(month_index, 0.0) for month_index in range(1, 13)), 2)
                column_figure_type = figure_type
            else:
                month_number = int(expression_label.split("_")[1])
                value = monthly_values.get(month_number, 0.0)
                column_figure_type = figure_type

            columns.append(
                report._build_column_dict(
                    value,
                    {**column, "figure_type": column_figure_type},
                    options=options,
                    currency=self.env.company.currency_id if column_figure_type == "monetary" else False,
                    digits=2,
                )
            )
        return columns
