from datetime import date

from odoo import api, models

from .tenenet_project_timesheet import HOUR_FIELD_BY_TYPE


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
        - Route remaining hours to tenenet.company.expense when not covered by projects
        - Trigger residual recompute for affected employee+periods
        """
        Timesheet = self.env["tenenet.project.timesheet"]
        Assignment = self.env["tenenet.project.assignment"]
        TenenetCost = self.env["tenenet.employee.tenenet.cost"]
        CompanyExpense = self.env["tenenet.company.expense"]

        for leave in self.filtered(lambda l: l.state == "validate"):
            employee = leave.employee_id
            if not employee:
                continue

            leave_type = leave.holiday_status_id
            date_from = leave.date_from.date() if leave.date_from else False
            date_to = leave.date_to.date() if leave.date_to else False
            if not date_from:
                continue

            # Get hour type mapping from leave type
            hour_type = self._get_hour_type_for_leave(leave_type)
            if not hour_type:
                # No mapping found - route all hours to company expense as general
                self._route_to_company_expense(leave, employee, date_from, date_to, None)
                continue

            affected_months = self._months_in_range(date_from, date_to or date_from)

            # Get all active assignments for this employee
            assignments = Assignment.search([
                ("employee_id", "=", employee.id),
                ("active", "=", True),
            ])

            for period_date in affected_months:
                period_first = period_date.replace(day=1)
                leave_hours_for_month = leave._hours_in_month(period_date)
                if not leave_hours_for_month:
                    continue

                # Find assignments with leave rules that include this leave type
                hours_allocated_to_projects = 0.0
                eligible_assignments = []

                for assignment in assignments:
                    # Check if this assignment is active for this period
                    if not assignment._is_period_in_scope(period_first):
                        continue

                    rule = self.env["tenenet.project.leave.rule"].search([
                        ("project_id", "=", assignment.project_id.id),
                        ("leave_type_id", "=", leave_type.id),
                        ("included", "=", True),
                    ], limit=1)
                    if rule:
                        eligible_assignments.append(assignment)

                if eligible_assignments:
                    # Distribute hours evenly among eligible assignments
                    hours_per_assignment = leave_hours_for_month / len(eligible_assignments)

                    for assignment in eligible_assignments:
                        timesheet = Timesheet.search([
                            ("assignment_id", "=", assignment.id),
                            ("period", "=", period_first),
                        ], limit=1)
                        if not timesheet:
                            timesheet = Timesheet.create({
                                "assignment_id": assignment.id,
                                "period": period_first,
                            })

                        leave_field = HOUR_FIELD_BY_TYPE.get(hour_type)
                        if leave_field:
                            current_hours = getattr(timesheet, leave_field) or 0.0
                            timesheet.write({
                                leave_field: current_hours + hours_per_assignment,
                                "leave_auto_synced": True,
                            })
                            hours_allocated_to_projects += hours_per_assignment

                # Route remaining hours to company expense
                unallocated_hours = leave_hours_for_month - hours_allocated_to_projects
                if unallocated_hours > 0.001:  # Small threshold to avoid floating point issues
                    CompanyExpense._create_or_update_expense(
                        employee=employee,
                        period=period_first,
                        expense_type=hour_type,
                        hours=unallocated_hours,
                        leave=leave,
                        note=f"Dovolenka typu '{leave_type.name}' nie je zahrnutá v žiadnom projekte" if not eligible_assignments else f"Zvyšok po rozdelení medzi {len(eligible_assignments)} projekt(y)",
                    )

                TenenetCost._sync_for_employee_period(employee.id, period_first)

    def _route_to_company_expense(self, leave, employee, date_from, date_to, hour_type):
        """Route all leave hours to company expense when no project covers them."""
        CompanyExpense = self.env["tenenet.company.expense"]
        TenenetCost = self.env["tenenet.employee.tenenet.cost"]

        affected_months = self._months_in_range(date_from, date_to or date_from)

        for period_date in affected_months:
            period_first = period_date.replace(day=1)
            leave_hours_for_month = leave._hours_in_month(period_date)
            if not leave_hours_for_month:
                continue

            # Use the expense type if available, otherwise use 'vacation' as fallback
            expense_type = hour_type or "vacation"

            CompanyExpense._create_or_update_expense(
                employee=employee,
                period=period_first,
                expense_type=expense_type,
                hours=leave_hours_for_month,
                leave=leave,
                note=f"Typ dovolenky '{leave.holiday_status_id.name}' nemá mapovanie na Tenenet kategóriu",
            )

            TenenetCost._sync_for_employee_period(employee.id, period_first)

    def _get_hour_type_for_leave(self, leave_type):
        """Get the Tenenet hour type for a leave type.

        First checks the explicit tenenet_hour_type field, then falls back to
        pattern matching on name/code.
        """
        # Use explicit mapping if available
        if hasattr(leave_type, "tenenet_hour_type") and leave_type.tenenet_hour_type:
            return leave_type.tenenet_hour_type

        # Fall back to pattern matching
        return self._leave_type_to_hour_type_by_pattern(leave_type)

    @api.model
    def _leave_type_to_hour_type_by_pattern(self, leave_type):
        """Map an hr.leave.type to hour type using name/code patterns."""
        name_lower = (leave_type.name or "").lower()
        code_lower = (getattr(leave_type, "code", "") or "").lower()

        # Vacation patterns
        if any(k in name_lower or k in code_lower for k in (
            "dovolenk", "vacation", "annual", "svadba", "pohreb", "narodenie",
            "studijn", "nahradn"
        )):
            return "vacation"

        # Sick leave patterns
        if any(k in name_lower or k in code_lower for k in (
            "pn", "ocr", "sick", "chorob", "matersk", "rodicovsk",
            "práceneschop", "osetrov"
        )):
            return "sick"

        # Doctor patterns
        if any(k in name_lower or k in code_lower for k in (
            "lekar", "lekár", "doctor", "medical", "spreva"
        )):
            return "doctor"

        # Holiday patterns
        if any(k in name_lower or k in code_lower for k in (
            "sviat", "holiday", "public", "platen"
        )):
            return "holidays"

        return None

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

    # Keep old method for backward compatibility
    @api.model
    def _leave_type_to_field(self, leave_type):
        """Map an hr.leave.type to the corresponding tenenet.project.timesheet field name.

        Deprecated: Use _get_hour_type_for_leave() instead.
        """
        hour_type = self._get_hour_type_for_leave(leave_type)
        if hour_type:
            return HOUR_FIELD_BY_TYPE.get(hour_type)
        return None
