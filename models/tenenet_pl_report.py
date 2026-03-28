from collections import defaultdict
from datetime import date

from odoo import fields, models


class TenenetPLReportHandler(models.AbstractModel):
    _name = "tenenet.pl.report.handler"
    _inherit = ["account.report.custom.handler"]
    _description = "TENENET P&L Report Handler"

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        custom_display_config = options["custom_display_config"]
        custom_display_config["css_custom_class"] = (
            custom_display_config.get("css_custom_class", "") + " tenenet_pl_report"
        ).strip()
        custom_display_config.setdefault("components", {})["AccountReportFilters"] = (
            "TenenetPLReportFilters"
        )

        selected_year = self._get_selected_year(options)
        self._set_year_options(options, selected_year)
        self.env["tenenet.pl.line"]._sync_for_year(selected_year)

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        selected_year = self._get_selected_year(options)
        programs = self._get_report_programs()
        if not programs:
            return []

        grouped_data = self._get_program_cost_buckets(selected_year, programs)
        lines = []
        total_profit_loss_by_month = defaultdict(float)

        sorted_program_rows = sorted(
            grouped_data.values(),
            key=lambda bucket: (bucket["program"].name or "").lower(),
        )
        for program_bucket in sorted_program_rows:
            program = program_bucket["program"]
            profit_loss_by_month = self._get_program_overview_profit_loss_by_month(
                program,
                selected_year,
                program_bucket,
            )
            for month_index in range(1, 13):
                total_profit_loss_by_month[month_index] += profit_loss_by_month[month_index]

            program_line_id = report._get_generic_line_id(
                "tenenet.program",
                program.id,
                markup="tenenet_pl_program",
            )
            lines.append((0, {
                "id": program_line_id,
                "name": program.display_name or program.name or "",
                "columns": self._build_columns(report, options, profit_loss_by_month, "monetary"),
                "level": 1,
                "unfoldable": True,
                "unfolded": bool(options.get("unfold_all") or program_line_id in (options.get("unfolded_lines") or [])),
                "expand_function": "_report_expand_unfoldable_line_tenenet_pl_program",
            }))

        lines.append((0, {
            "id": report._get_generic_line_id(
                None,
                None,
                markup="tenenet_pl_program_total",
            ),
            "name": "Zisk / strata spolu",
            "columns": self._build_columns(report, options, total_profit_loss_by_month, "monetary"),
            "level": 1,
        }))
        return lines

    def _get_program_overview_profit_loss_by_month(self, program, selected_year, program_bucket):
        detail_rows = self._get_program_detail_rows(program, selected_year)
        profit_loss_values = self._extract_profit_loss_values(detail_rows)
        if profit_loss_values:
            return profit_loss_values

        amount_by_month = (
            program_bucket["timesheet_amount"]
            if program_bucket["timesheet_count"]
            else program_bucket["pl_line_amount"]
        )
        profit_loss_by_month = defaultdict(float)
        for month_index in range(1, 13):
            profit_loss_by_month[month_index] = -(amount_by_month.get(month_index, 0.0) or 0.0)
        return profit_loss_by_month

    def _report_expand_unfoldable_line_tenenet_pl_program(
        self, line_dict_id, groupby, options, progress, offset, unfold_all_batch_data=None
    ):
        report = self.env["account.report"].browse(options["report_id"])
        markup, model, record_id = report._parse_line_id(line_dict_id)[-1]
        if model != "tenenet.program":
            return {"lines": []}

        program = self.env["tenenet.program"].browse(record_id).exists()
        if not program:
            return {"lines": []}

        selected_year = self._get_selected_year(options)
        project_rows = self._get_program_project_profit_rows(program, selected_year)
        detail_rows = self._get_program_detail_rows(program, selected_year)
        lines = []
        for index, project_row in enumerate(project_rows, start=1):
            lines.append(
                self._build_project_detail_line(
                    report,
                    options,
                    line_dict_id,
                    program,
                    project_row,
                    index,
                    level=2,
                )
            )

        detail_row_offset = len(lines)
        for index, detail_row in enumerate(detail_rows, start=1):
            lines.append(
                self._build_detail_line(
                    report,
                    options,
                    line_dict_id,
                    program,
                    detail_row,
                    detail_row_offset + index,
                )
            )
        return {
            "lines": lines,
            "offset_increment": len(lines),
            "has_more": False,
            "progress": progress,
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

    def _get_year_pl_lines(self, selected_year):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        return self.env["tenenet.pl.line"].search(
            [
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ],
            order="program_id, employee_id, period",
        )

    def _get_year_program_timesheets(self, selected_year):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        return self.env["tenenet.project.timesheet"].with_context(active_test=False).search(
            [
                ("project_id.program_ids", "!=", False),
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ],
            order="project_id, employee_id, period",
        )

    def _get_report_programs(self):
        return self.env["tenenet.program"].with_context(active_test=False).search([], order="name")

    def _get_program_cost_buckets(self, selected_year, programs):
        grouped_data = {
            program.id: {
                "program": program,
                "timesheet_amount": defaultdict(float),
                "timesheet_count": 0,
                "pl_line_amount": defaultdict(float),
                "pl_line_count": 0,
            }
            for program in programs
        }

        timesheets = self._get_year_program_timesheets(selected_year)
        for timesheet in timesheets:
            for program in timesheet.project_id.program_ids:
                if not program:
                    continue
                if program.id not in grouped_data:
                    grouped_data[program.id] = {
                        "program": program,
                        "timesheet_amount": defaultdict(float),
                        "timesheet_count": 0,
                        "pl_line_amount": defaultdict(float),
                        "pl_line_count": 0,
                    }
                grouped_data[program.id]["timesheet_amount"][timesheet.period.month] += timesheet.total_labor_cost or 0.0
                grouped_data[program.id]["timesheet_count"] += 1

        pl_lines = self._get_year_pl_lines(selected_year)
        for pl_line in pl_lines:
            program = pl_line.program_id
            if program.id not in grouped_data:
                grouped_data[program.id] = {
                    "program": program,
                    "timesheet_amount": defaultdict(float),
                    "timesheet_count": 0,
                    "pl_line_amount": defaultdict(float),
                    "pl_line_count": 0,
                }
            grouped_data[program.id]["pl_line_amount"][pl_line.period.month] += pl_line.amount or 0.0
            grouped_data[program.id]["pl_line_count"] += 1
        return grouped_data

    def _build_detail_line(self, report, options, parent_line_id, program, detail_row, sequence):
        return {
            "id": report._get_generic_line_id(
                None,
                None,
                parent_line_id=parent_line_id,
                markup=f"tenenet_pl_program_detail_{program.id}_{sequence}",
            ),
            "name": detail_row["name"],
            "columns": self._build_columns(
                report,
                options,
                detail_row["values"],
                detail_row["figure_type"],
            ),
            "level": detail_row["level"],
            "parent_id": parent_line_id,
        }

    def _build_project_detail_line(self, report, options, parent_line_id, program, project_row, sequence, level=2):
        return {
            "id": report._get_generic_line_id(
                "tenenet.project",
                project_row["project"].id,
                parent_line_id=parent_line_id,
                markup=f"tenenet_pl_program_project_{program.id}_{sequence}",
            ),
            "name": project_row["name"],
            "columns": self._build_columns(report, options, project_row["values"], "monetary"),
            "level": level,
            "parent_id": parent_line_id,
        }

    def _build_project_section_line(self, report, options, parent_line_id, program, section_name, sequence):
        return {
            "id": report._get_generic_line_id(
                None,
                None,
                parent_line_id=parent_line_id,
                markup=f"tenenet_pl_program_project_section_{program.id}_{sequence}",
            ),
            "markup": "tenenet_pl_project_section",
            "name": section_name,
            "columns": self._build_columns(report, options, defaultdict(float), "string"),
            "level": 2,
            "parent_id": parent_line_id,
        }

    def _get_program_detail_rows(self, program, selected_year):
        return self._get_program_detail_rows_from_odoo(program, selected_year)

    def _get_program_project_profit_rows(self, program, selected_year):
        project_rows = []
        for project in self._get_program_projects(program):
            profit_loss_by_month = self._get_project_profit_loss_by_month(project, selected_year)
            if not any(profit_loss_by_month.values()):
                continue
            project_rows.append({
                "project": project,
                "name": self._get_project_line_name(project),
                "values": profit_loss_by_month,
            })
        return sorted(project_rows, key=lambda row: (row["name"] or "").lower())

    def _get_project_profit_loss_by_month(self, project, selected_year):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)

        receipts = self.env["tenenet.project.receipt"].search([
            ("project_id", "=", project.id),
            ("year", "=", selected_year),
        ])
        timesheets = self.env["tenenet.project.timesheet"].with_context(active_test=False).search([
            ("project_id", "=", project.id),
            ("period", ">=", year_start),
            ("period", "<=", year_end),
        ])

        income_by_month = defaultdict(float)
        if receipts:
            monthly_income = sum(receipts.mapped("amount")) / 12.0
            for month_index in range(1, 13):
                income_by_month[month_index] = monthly_income

        labor_cost_by_month = defaultdict(float)
        for timesheet in timesheets:
            labor_cost_by_month[timesheet.period.month] -= timesheet.total_labor_cost or 0.0

        profit_loss_by_month = defaultdict(float)
        for month_index in range(1, 13):
            profit_loss_by_month[month_index] = income_by_month[month_index] + labor_cost_by_month[month_index]
        return profit_loss_by_month

    def _get_program_projects(self, program):
        return self.env["tenenet.project"].with_context(active_test=False).search(
            [("program_ids", "in", [program.id])],
            order="name",
        )

    def _get_project_line_name(self, project):
        return (project.name or "").strip() or project.display_name or ""

    def _extract_detail_row_values(self, detail_rows, row_name):
        for detail_row in detail_rows:
            if detail_row["name"] == row_name:
                return detail_row["values"]
        return False

    def _extract_profit_loss_values(self, detail_rows):
        target_name = "Zisk/strata - za program"
        for detail_row in detail_rows:
            if detail_row["name"] == target_name:
                return detail_row["values"]
        return False

    def _get_program_detail_rows_from_odoo(self, program, selected_year):
        year_start = date(selected_year, 1, 1)
        year_end = date(selected_year, 12, 31)
        timesheets = self.env["tenenet.project.timesheet"].with_context(active_test=False).search(
            [
                ("project_id.program_ids", "in", [program.id]),
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ]
        )
        pl_lines = self.env["tenenet.pl.line"].search(
            [
                ("program_id", "=", program.id),
                ("period", ">=", year_start),
                ("period", "<=", year_end),
            ]
        )
        receipts = self.env["tenenet.project.receipt"].search([
            ("project_id.program_ids", "in", [program.id]),
            ("year", "=", selected_year),
        ])

        income_by_month = defaultdict(float)
        if receipts:
            monthly_income = sum(receipts.mapped("amount")) / 12.0
            for month_index in range(1, 13):
                income_by_month[month_index] = monthly_income

        labor_cost_by_month = defaultdict(float)
        labor_cost_source = timesheets if timesheets else pl_lines
        for line in labor_cost_source:
            amount = line.total_labor_cost if timesheets else line.amount
            labor_cost_by_month[line.period.month] -= amount or 0.0

        total_result_by_month = defaultdict(float)
        for month_index in range(1, 13):
            total_result_by_month[month_index] = income_by_month[month_index] + labor_cost_by_month[month_index]

        zero_by_month = defaultdict(float)
        rows = [
            {
                "name": "Príjmy/výnosy",
                "values": defaultdict(float),
                "figure_type": "string",
                "level": 2,
            },
            {
                "name": "Príjmy spolu",
                "values": income_by_month,
                "figure_type": "monetary",
                "level": 3,
            },
            {
                "name": "Náklady",
                "values": defaultdict(float),
                "figure_type": "string",
                "level": 2,
            },
            {
                "name": "Mzdové náklady - program",
                "values": labor_cost_by_month,
                "figure_type": "monetary",
                "level": 3,
            },
            {
                "name": "Stravné a iné",
                "values": zero_by_month.copy(),
                "figure_type": "monetary",
                "level": 3,
            },
            {
                "name": "Zisk/strata - vykrytie mzdových nákladov",
                "values": total_result_by_month,
                "figure_type": "monetary",
                "level": 3,
            },
            {
                "name": "Admin a manažérske náklady",
                "values": defaultdict(float),
                "figure_type": "string",
                "level": 2,
            },
            {
                "name": "Mzdové náklady - podporné odd./admin",
                "values": zero_by_month.copy(),
                "figure_type": "monetary",
                "level": 3,
            },
            {
                "name": "Mzdové náklady - manažment",
                "values": zero_by_month.copy(),
                "figure_type": "monetary",
                "level": 3,
            },
            {
                "name": "Prevádzkové náklady",
                "values": zero_by_month.copy(),
                "figure_type": "monetary",
                "level": 3,
            },
            {
                "name": "Zisk/strata - za program",
                "values": total_result_by_month,
                "figure_type": "monetary",
                "level": 3,
            },
        ]
        return rows

    def _build_columns(self, report, options, monthly_values, figure_type):
        columns = []
        for column in options["columns"]:
            expression_label = column["expression_label"]
            if figure_type == "string":
                value = ""
                column_figure_type = "string"
            elif expression_label == "h1_total":
                value = sum(monthly_values.get(month_index, 0.0) for month_index in range(1, 7))
                column_figure_type = figure_type
            elif expression_label == "year_total":
                value = sum(monthly_values.get(month_index, 0.0) for month_index in range(1, 13))
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
