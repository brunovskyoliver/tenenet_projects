import logging
from datetime import date, timedelta

from odoo import api, models

from .tenenet_project_timesheet import HOUR_FIELD_BY_TYPE

_logger = logging.getLogger(__name__)


class HrLeave(models.Model):
    _inherit = "hr.leave"

    def action_approve(self, check_state=True):
        """Override to sync leave hours to timesheets after approval."""
        _logger.warning("=== TENENET: action_approve called for leaves: %s ===", self.ids)
        result = super().action_approve(check_state=check_state)
        # Sync timesheets for leaves that are now validated
        validated_leaves = self.filtered(lambda l: l.state == 'validate')
        _logger.warning("=== TENENET: Validated leaves to sync: %s ===", validated_leaves.ids)
        if validated_leaves:
            validated_leaves._sync_tenenet_timesheets()
        return result

    def _action_validate(self, check_state=True):
        """Override to sync leave hours to timesheets after validation."""
        _logger.warning("=== TENENET: _action_validate called for leaves: %s ===", self.ids)
        result = super()._action_validate(check_state=check_state)
        self._sync_tenenet_timesheets()
        return result

    def _sync_tenenet_timesheets(self):
        """Sync approved leave hours into tenenet.project.timesheet lines.

        Logic:
        - By default, leave hours are allocated to ALL eligible project assignments
        - A project can EXCLUDE a leave type by setting included=False in leave rules
        - Only hours not covered by any project go to tenenet.company.expense
        """
        Timesheet = self.env["tenenet.project.timesheet"]
        Assignment = self.env["tenenet.project.assignment"]
        TenenetCost = self.env["tenenet.employee.tenenet.cost"]
        CompanyExpense = self.env["tenenet.company.expense"]
        LeaveRule = self.env["tenenet.project.leave.rule"]

        for leave in self.filtered(lambda l: l.state == "validate"):
            employee = leave.employee_id
            if not employee:
                _logger.debug("Leave %s: No employee, skipping", leave.id)
                continue

            leave_type = leave.holiday_status_id
            date_from = leave.date_from.date() if leave.date_from else False
            date_to = leave.date_to.date() if leave.date_to else False
            if not date_from:
                _logger.debug("Leave %s: No date_from, skipping", leave.id)
                continue

            _logger.info(
                "Syncing leave %s: employee=%s, type=%s, dates=%s to %s, hours=%s",
                leave.id, employee.name, leave_type.name, date_from, date_to, leave.number_of_hours
            )

            # Get hour type mapping from leave type
            hour_type = self._get_hour_type_for_leave(leave_type)
            _logger.warning("Leave %s: hour_type=%s", leave.id, hour_type)

            if not hour_type:
                # No mapping found - route all hours to company expense
                _logger.warning(
                    "Leave %s: No hour_type mapping for '%s', routing to company expense",
                    leave.id, leave_type.name
                )
                self._route_to_company_expense(leave, employee, date_from, date_to, None)
                continue

            affected_months = self._months_in_range(date_from, date_to or date_from)
            _logger.warning("Leave %s: affected_months=%s", leave.id, affected_months)

            # Get all active assignments for this employee
            assignments = Assignment.search([
                ("employee_id", "=", employee.id),
                ("active", "=", True),
            ])
            _logger.warning(
                "Leave %s: Found %d active assignments: %s",
                leave.id, len(assignments),
                [(a.id, a.project_id.name) for a in assignments]
            )

            for period_date in affected_months:
                period_first = period_date.replace(day=1)
                leave_hours_for_month = leave._hours_in_month(period_date)
                
                _logger.warning(
                    "Leave %s: Processing period=%s, hours_for_month=%s",
                    leave.id, period_first, leave_hours_for_month
                )
                
                if not leave_hours_for_month:
                    _logger.warning("Leave %s: No hours for period %s, skipping", leave.id, period_first)
                    continue

                # Find eligible assignments (default: included, unless explicitly excluded)
                hours_allocated_to_projects = 0.0
                eligible_assignments = []

                for assignment in assignments:
                    project = assignment.project_id
                    
                    # Check if this assignment is active for this period
                    in_scope = assignment._is_period_in_scope(period_first)
                    _logger.warning(
                        "Leave %s: Assignment %s (project=%s) in_scope=%s",
                        leave.id, assignment.id, project.name, in_scope
                    )
                    
                    if not in_scope:
                        continue

                    # Check leave rule - DEFAULT IS INCLUDED (paid by project)
                    # Only exclude if there's an explicit rule with included=False
                    rule = LeaveRule.search([
                        ("project_id", "=", project.id),
                        ("leave_type_id", "=", leave_type.id),
                    ], limit=1)

                    if rule:
                        _logger.warning(
                            "Leave %s: Found rule for project=%s, leave_type=%s, included=%s",
                            leave.id, project.name, leave_type.name, rule.included
                        )
                        if not rule.included:
                            # Explicitly excluded
                            _logger.warning(
                                "Leave %s: Project %s explicitly excludes leave type %s",
                                leave.id, project.name, leave_type.name
                            )
                            continue
                    else:
                        # No rule = default included
                        _logger.warning(
                            "Leave %s: No rule for project=%s, leave_type=%s - default INCLUDED",
                            leave.id, project.name, leave_type.name
                        )

                    eligible_assignments.append(assignment)

                _logger.warning(
                    "Leave %s: Period %s - %d eligible assignments: %s",
                    leave.id, period_first, len(eligible_assignments),
                    [(a.id, a.project_id.name) for a in eligible_assignments]
                )

                if eligible_assignments:
                    # Distribute hours evenly among eligible assignments
                    hours_per_assignment = leave_hours_for_month / len(eligible_assignments)
                    _logger.warning(
                        "Leave %s: Distributing %.2f hours each to %d assignments",
                        leave.id, hours_per_assignment, len(eligible_assignments)
                    )

                    for assignment in eligible_assignments:
                        timesheet = Timesheet.search([
                            ("assignment_id", "=", assignment.id),
                            ("period", "=", period_first),
                        ], limit=1)
                        
                        if not timesheet:
                            _logger.warning(
                                "Leave %s: Creating timesheet for assignment=%s, period=%s",
                                leave.id, assignment.id, period_first
                            )
                            timesheet = Timesheet.create({
                                "assignment_id": assignment.id,
                                "period": period_first,
                            })

                        leave_field = HOUR_FIELD_BY_TYPE.get(hour_type)
                        _logger.warning(
                            "Leave %s: hour_type=%s -> field=%s",
                            leave.id, hour_type, leave_field
                        )
                        
                        if leave_field:
                            current_hours = getattr(timesheet, leave_field) or 0.0
                            new_hours = current_hours + hours_per_assignment
                            _logger.warning(
                                "Leave %s: Updating timesheet %s.%s: %.2f -> %.2f (+%.2f)",
                                leave.id, timesheet.id, leave_field,
                                current_hours, new_hours, hours_per_assignment
                            )
                            timesheet.write({
                                leave_field: new_hours,
                                "leave_auto_synced": True,
                            })
                            hours_allocated_to_projects += hours_per_assignment
                        else:
                            _logger.warning(
                                "Leave %s: No field mapping for hour_type=%s",
                                leave.id, hour_type
                            )

                # Route remaining hours to company expense
                unallocated_hours = leave_hours_for_month - hours_allocated_to_projects
                _logger.warning(
                    "Leave %s: Period %s - allocated=%.2f, unallocated=%.2f",
                    leave.id, period_first, hours_allocated_to_projects, unallocated_hours
                )
                
                if unallocated_hours > 0.001:  # Small threshold to avoid floating point issues
                    note = (
                        f"Žiadny projekt nepokrýva typ '{leave_type.name}'"
                        if not eligible_assignments
                        else f"Zvyšok po rozdelení medzi {len(eligible_assignments)} projekt(y)"
                    )
                    _logger.warning(
                        "Leave %s: Routing %.2f unallocated hours to company expense: %s",
                        leave.id, unallocated_hours, note
                    )
                    CompanyExpense._create_or_update_expense(
                        employee=employee,
                        period=period_first,
                        expense_type=hour_type,
                        hours=unallocated_hours,
                        leave=leave,
                        note=note,
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

            _logger.info(
                "Leave %s: Routing %.2f hours to company expense (type=%s, period=%s)",
                leave.id, leave_hours_for_month, expense_type, period_first
            )

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
            _logger.debug(
                "Leave type %s: Using explicit tenenet_hour_type=%s",
                leave_type.name, leave_type.tenenet_hour_type
            )
            return leave_type.tenenet_hour_type

        # Fall back to pattern matching
        hour_type = self._leave_type_to_hour_type_by_pattern(leave_type)
        _logger.debug(
            "Leave type %s: Pattern matching returned hour_type=%s",
            leave_type.name, hour_type
        )
        return hour_type

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
        """Return number of leave hours falling in the given month.
        
        Logic:
        - If leave type request_unit is 'hour': use number_of_hours directly
        - If leave type request_unit is 'day' or 'half_day': calculate from 
          number_of_days * employee's hours_per_day from resource_calendar_id
        
        For multi-month leaves, calculates the proportion of hours/days
        that fall within the given month.
        """
        if not self.date_from or not self.date_to:
            return self._get_total_leave_hours()
        
        date_from = self.date_from.date()
        date_to = self.date_to.date()
        
        # For the calculation, we need date_to to be exclusive (day after last leave day)
        date_to_exclusive = date_to + timedelta(days=1)
        
        month_start = period_date.replace(day=1)
        if month_start.month == 12:
            month_end = date(month_start.year + 1, 1, 1)
        else:
            month_end = date(month_start.year, month_start.month + 1, 1)

        overlap_start = max(date_from, month_start)
        overlap_end = min(date_to_exclusive, month_end)
        
        if overlap_start >= overlap_end:
            return 0.0

        # Total days in leave (inclusive)
        total_days = (date_to - date_from).days + 1
        # Days overlapping with this month
        overlap_days = (overlap_end - overlap_start).days
        
        ratio = overlap_days / total_days if total_days > 0 else 1.0
        
        total_hours = self._get_total_leave_hours()
        hours = round(total_hours * ratio, 2)
        
        _logger.warning(
            "Leave %s: _hours_in_month period=%s, date_from=%s, date_to=%s, "
            "overlap_days=%d/%d, ratio=%.2f, total_hours=%.2f, result=%.2f",
            self.id, period_date, date_from, date_to,
            overlap_days, total_days, ratio, total_hours, hours
        )
        
        return hours

    def _get_total_leave_hours(self):
        """Get total hours for this leave based on request_unit type.
        
        - For hour-based leaves: use number_of_hours
        - For day-based leaves: use number_of_days * employee's hours_per_day
        """
        leave_type = self.holiday_status_id
        request_unit = leave_type.request_unit if leave_type else 'day'
        
        if request_unit == 'hour':
            # Hour-based leave - use hours directly
            hours = self.number_of_hours or 0.0
            _logger.warning(
                "Leave %s: Hour-based leave, number_of_hours=%.2f",
                self.id, hours
            )
            return hours
        
        # Day-based leave - calculate from days * hours_per_day
        days = self.number_of_days or 0.0
        hours_per_day = self._get_employee_hours_per_day()
        hours = days * hours_per_day
        
        _logger.warning(
            "Leave %s: Day-based leave, number_of_days=%.2f, hours_per_day=%.2f, total=%.2f",
            self.id, days, hours_per_day, hours
        )
        return hours

    def _get_employee_hours_per_day(self):
        """Get the employee's standard hours per day from their resource calendar."""
        employee = self.employee_id
        if not employee:
            return 8.0  # Default fallback
        
        calendar = employee.resource_calendar_id
        if not calendar:
            return 8.0  # Default fallback
        
        # Calculate hours per day from calendar
        # hours_per_day is a computed field on resource.calendar
        hours_per_day = calendar.hours_per_day or 8.0
        
        _logger.warning(
            "Leave %s: Employee %s calendar=%s, hours_per_day=%.2f",
            self.id, employee.name, calendar.name, hours_per_day
        )
        return hours_per_day

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
