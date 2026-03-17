from datetime import date

from odoo import api, models


class HrLeave(models.Model):
    _inherit = "hr.leave"

    def action_validate(self):
        result = super().action_validate()
        self._sync_tenenet_timesheets()
        return result

    def _sync_tenenet_timesheets(self):
        """Sync approved leave hours into tenenet.project.timesheet lines.

        For each validated leave:
        - Find active project assignments for the employee covering the leave period
        - Check per-project leave rules (tenenet.project.leave.rule)
        - Distribute hours to timesheet lines where included=True
        - Trigger residual recompute for affected employee+periods
        """
        Timesheet = self.env["tenenet.project.timesheet"]
        Assignment = self.env["tenenet.project.assignment"]
        TenenetCost = self.env["tenenet.employee.tenenet.cost"]

        for leave in self.filtered(lambda l: l.state == "validate"):
            employee = leave.employee_id
            if not employee:
                continue

            leave_type = leave.holiday_status_id
            date_from = leave.date_from.date() if leave.date_from else False
            date_to = leave.date_to.date() if leave.date_to else False
            if not date_from:
                continue

            affected_months = self._months_in_range(date_from, date_to or date_from)

            assignments = Assignment.search([
                ("employee_id", "=", employee.id),
                ("active", "=", True),
            ])

            for period_date in affected_months:
                period_first = period_date.replace(day=1)
                leave_hours_for_month = leave._hours_in_month(period_date)
                if not leave_hours_for_month:
                    continue
                for assignment in assignments:
                    rule = self.env["tenenet.project.leave.rule"].search([
                        ("project_id", "=", assignment.project_id.id),
                        ("leave_type_id", "=", leave_type.id),
                        ("included", "=", True),
                    ], limit=1)
                    if not rule:
                        continue

                    timesheet = Timesheet.search([
                        ("assignment_id", "=", assignment.id),
                        ("period", "=", period_first),
                    ], limit=1)
                    if not timesheet:
                        timesheet = Timesheet.create({
                            "assignment_id": assignment.id,
                            "period": period_first,
                        })

                    leave_field = self._leave_type_to_field(leave_type)
                    if leave_field:
                        timesheet.write({
                            leave_field: (getattr(timesheet, leave_field) or 0.0) + leave_hours_for_month,
                            "leave_auto_synced": True,
                        })

                TenenetCost._sync_for_employee_period(employee.id, period_first)

    @api.model
    def _months_in_range(self, date_from, date_to):
        """Return a list of date objects (1st of month) for all months touched by the range."""
        months = []
        current = date_from.replace(day=1)
        end = date_to.replace(day=1)
        while current <= end:
            months.append(current)
            month = current.month + 1
            year = current.year
            if month > 12:
                month = 1
                year += 1
            current = date(year, month, 1)
        return months

    def _hours_in_month(self, period_date):
        """Return number of leave hours falling in the given month (approximated from number_of_days)."""
        if not self.date_from or not self.date_to:
            return (self.number_of_hours or 0.0)
        date_from = self.date_from.date()
        date_to = self.date_to.date()
        month_start = period_date.replace(day=1)
        if month_start.month == 12:
            month_end = date(month_start.year + 1, 1, 1)
        else:
            month_end = date(month_start.year, month_start.month + 1, 1)

        overlap_start = max(date_from, month_start)
        overlap_end = min(date_to, month_end)
        if overlap_start >= overlap_end:
            return 0.0

        total_days = (date_to - date_from).days or 1
        overlap_days = (overlap_end - overlap_start).days
        ratio = overlap_days / total_days
        return round((self.number_of_hours or 0.0) * ratio, 2)

    @api.model
    def _leave_type_to_field(self, leave_type):
        """Map an hr.leave.type to the corresponding tenenet.project.timesheet field name.

        Falls back to mapping by leave type code or name patterns.
        """
        name_lower = (leave_type.name or "").lower()
        code_lower = (leave_type.code or "").lower() if hasattr(leave_type, "code") else ""
        if any(k in name_lower or k in code_lower for k in ("dovolenk", "vacation", "annual")):
            return "hours_vacation"
        if any(k in name_lower or k in code_lower for k in ("pn", "ocr", "sick", "chorob")):
            return "hours_sick"
        if any(k in name_lower or k in code_lower for k in ("lekar", "lekár", "doctor", "medical")):
            return "hours_doctor"
        if any(k in name_lower or k in code_lower for k in ("sviat", "holiday", "public")):
            return "hours_holidays"
        return None
