from odoo import fields, models


class TenenetUtilizationReportHandler(models.AbstractModel):
    _name = "tenenet.utilization.report.handler"
    _inherit = ["account.report.custom.handler"]
    _description = "TENENET Utilization Report Handler"

    _PERCENTAGE_COLUMNS = {"utilization_rate", "non_project_rate"}
    _FLOAT_COLUMNS = {
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

    def _dynamic_lines_generator(self, report, options, all_column_groups_expression_totals, warnings=None):
        period = self._get_selected_month_start(report, options)
        self.env["tenenet.utilization"].sudo()._sync_for_period(period)
        utilization_records = self._get_utilization_records(period)
        return [
            (0, self._get_report_line(report, options, utilization))
            for utilization in utilization_records
        ]

    def _get_selected_month_start(self, report, options):
        date_to = options.get("date", {}).get("date_to") or fields.Date.context_today(self)
        return self.env["tenenet.utilization"]._normalize_period(date_to)

    def _get_utilization_records(self, period):
        records = self.env["tenenet.utilization"].search([("period", "=", period)])
        return records.sorted(
            key=lambda rec: (
                (rec.manager_name or "").lower(),
                (rec.employee_id.name or "").lower(),
                rec.employee_id.id,
            )
        )

    def _get_report_line(self, report, options, utilization):
        columns = []
        for column in options["columns"]:
            label = column["expression_label"]
            columns.append(
                report._build_column_dict(
                    self._get_column_value(utilization, label),
                    column,
                    options=options,
                    digits=2,
                )
            )

        return {
            "id": report._get_generic_line_id("hr.employee", utilization.employee_id.id, markup="tenenet_utilization"),
            "name": utilization.employee_id.name or "",
            "columns": columns,
            "level": 2,
        }

    def _get_column_value(self, utilization, label):
        if label == "employee_name":
            return utilization.employee_id.name or ""
        if label == "manager_name":
            return utilization.manager_name or ""
        return utilization[label]

