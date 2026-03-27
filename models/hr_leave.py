import logging
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class HrLeave(models.Model):
    _inherit = "hr.leave"

    tenenet_override_assignment_id = fields.Many2one(
        "tenenet.project.assignment",
        string="Override: priradenie (Tenenet)",
        ondelete="set null",
        help="Ak je nastavené, dovolenka bude priradená k tomuto priradeniu bez ohľadu na pravidlá.",
    )
    tenenet_override_is_internal = fields.Boolean(
        string="Override: interné náklady",
        default=False,
        help="Ak je zaškrtnuté, dovolenka bude vždy priradená k interným nákladom TENENET.",
    )

    def action_approve(self, check_state=True):
        """Approve leave and synchronize TENENET leave timesheets from this action."""
        self._ensure_tenenet_leave_mapping()
        result = super(HrLeave, self.with_context(skip_tenenet_leave_sync=True)).action_approve(
            check_state=check_state
        )
        self.filtered(lambda leave: leave.state == "validate")._sync_tenenet_timesheets()
        return result

    def _action_validate(self, check_state=True):
        """Keep native validation behavior; sync ownership is in action_approve."""
        return super(HrLeave, self.with_context(skip_tenenet_leave_sync=True))._action_validate(
            check_state=check_state
        )

    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get("skip_tenenet_leave_sync"):
            return result

        sync_fields = {
            "state",
            "employee_id",
            "holiday_status_id",
            "date_from",
            "date_to",
            "request_date_from",
            "request_date_to",
            "request_hour_from",
            "request_hour_to",
            "number_of_days",
            "number_of_hours",
            "tenenet_override_assignment_id",
            "tenenet_override_is_internal",
        }
        if sync_fields & set(vals):
            self._sync_tenenet_timesheets()
        return result

    def unlink(self):
        self._clear_tenenet_sync_entries()
        return super().unlink()

    def _clear_tenenet_sync_entries(self):
        SyncEntry = self.env["tenenet.project.leave.sync.entry"].sudo()
        InternalExpense = self.env["tenenet.internal.expense"].sudo()
        for leave in self:
            SyncEntry._replace_for_leave(leave, [])
            InternalExpense.search([("leave_id", "=", leave.id)]).unlink()

    def _sync_tenenet_timesheets(self):
        """Hard-replace leave synchronization into TENENET timesheets via ledger rows.

        Algorithm (per affected month):
        1. If tenenet_override_is_internal → force internal expense, skip all rules.
        2. If tenenet_override_assignment_id → force that specific assignment.
        3. Otherwise: find eligible assignments (leave rule included=True, limit not exceeded),
           pick the ONE with the LEAST used leave hours this year.
        4. If no eligible assignment → create tenenet.internal.expense (category=leave).
        """
        Assignment = self.env["tenenet.project.assignment"].sudo()
        LeaveRule = self.env["tenenet.project.leave.rule"].sudo()
        SyncEntry = self.env["tenenet.project.leave.sync.entry"].sudo()
        InternalExpense = self.env["tenenet.internal.expense"].sudo()

        for leave in self:
            if leave.state != "validate":
                SyncEntry._replace_for_leave(leave, [])
                InternalExpense.search([("leave_id", "=", leave.id)]).unlink()
                continue

            employee = leave.employee_id
            if not employee:
                SyncEntry._replace_for_leave(leave, [])
                InternalExpense.search([("leave_id", "=", leave.id)]).unlink()
                continue

            leave_type = leave.holiday_status_id
            hour_type = self._get_hour_type_for_leave(leave_type)
            if not hour_type:
                raise ValidationError(
                    f"Typ dovolenky '{leave_type.display_name}' nemá mapovanie na TENENET kategóriu hodín. "
                    "Nastavte pole 'Tenenet typ hodín' na type dovolenky."
                )

            date_from = leave.date_from.date() if leave.date_from else False
            date_to = leave.date_to.date() if leave.date_to else date_from
            if not date_from:
                SyncEntry._replace_for_leave(leave, [])
                InternalExpense.search([("leave_id", "=", leave.id)]).unlink()
                continue

            # Clear any prior internal expense records for this leave (re-sync scenario)
            InternalExpense.search([("leave_id", "=", leave.id)]).unlink()

            affected_months = self._months_in_range(date_from, date_to)
            allocations = []

            # Pre-load all active non-internal assignments for the employee
            all_assignments = Assignment.search([
                ("employee_id", "=", employee.id),
                ("active", "=", True),
                ("project_id.is_tenenet_internal", "=", False),
            ])

            for period_date in affected_months:
                period_first = period_date.replace(day=1)
                leave_hours_for_month = leave._hours_in_month(period_date)
                if leave_hours_for_month <= 0.001:
                    continue

                # ── Override: force to internal expense ──────────────────────
                if leave.tenenet_override_is_internal:
                    source = leave.tenenet_override_assignment_id or False
                    self._create_leave_internal_expense(
                        leave, employee, period_first,
                        leave_hours_for_month, hour_type, source,
                        note="Manuálne nastavené ako interný náklad.",
                    )
                    continue

                # ── Override: force to a specific assignment ──────────────────
                if leave.tenenet_override_assignment_id:
                    allocations.append({
                        "assignment_id": leave.tenenet_override_assignment_id.id,
                        "period": period_first,
                        "hour_type": hour_type,
                        "hours": leave_hours_for_month,
                    })
                    continue

                # ── Auto algorithm ─────────────────────────────────────────────
                in_scope = all_assignments.filtered(
                    lambda a: a._is_period_in_scope(period_first)
                )

                rules = LeaveRule.search([
                    ("leave_type_id", "=", leave_type.id),
                    ("included", "=", True),
                    ("project_id", "in", in_scope.mapped("project_id").ids),
                ])
                allowed_project_ids = set(rules.mapped("project_id").ids)
                rule_by_project = {r.project_id.id: r for r in rules}

                # Candidates: assignments whose project allows this leave type
                candidates = in_scope.filtered(
                    lambda a: a.project_id.id in allowed_project_ids
                )

                # Filter by yearly max limit
                year = period_first.year
                used_map = self._get_used_leave_hours_for_year(
                    employee.id,
                    candidates.ids,
                    leave_type.id,
                    year,
                )
                eligible = self.env["tenenet.project.assignment"]
                over_limit_candidate = self.env["tenenet.project.assignment"]

                for assignment in candidates:
                    rule = rule_by_project.get(assignment.project_id.id)
                    max_days = rule.max_leaves_per_year_days if rule else 0.0
                    if max_days > 0.0:
                        max_hours = max_days * (employee.work_hours or 8.0)
                        used_hours = used_map.get(assignment.id, 0.0)
                        if used_hours >= max_hours:
                            if not over_limit_candidate:
                                over_limit_candidate = assignment
                            continue
                    eligible |= assignment

                if eligible:
                    chosen = self._pick_assignment_least_used(eligible, used_map)
                    allocations.append({
                        "assignment_id": chosen.id,
                        "period": period_first,
                        "hour_type": hour_type,
                        "hours": leave_hours_for_month,
                    })
                else:
                    # No eligible assignment → internal expense
                    source = over_limit_candidate or (candidates[:1] or all_assignments[:1])
                    note = (
                        "Žiadne priradenie s platným pravidlom dovolenky pre tento typ."
                        if not candidates
                        else "Všetky priradenia prekročili ročný limit dovolenky."
                    )
                    self._create_leave_internal_expense(
                        leave, employee, period_first,
                        leave_hours_for_month, hour_type, source or False,
                        note=note,
                    )

            _logger.info(
                "TENENET leave sync for leave %s -> %d ledger rows",
                leave.id,
                len(allocations),
            )
            SyncEntry._replace_for_leave(leave, allocations)

        self.env["tenenet.utilization"]._sync_current_period()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_used_leave_hours_for_year(self, employee_id, assignment_ids, leave_type_id, year):
        """Return {assignment_id: total_hours} for the given employee/assignments/leave_type/year."""
        if not assignment_ids:
            return {}
        SyncEntry = self.env["tenenet.project.leave.sync.entry"].sudo()
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)

        # Map leave_type_id → hour_type first
        leave_type = self.env["hr.leave.type"].browse(leave_type_id)
        hour_type = self._get_hour_type_for_leave(leave_type)

        domain = [
            ("employee_id", "=", employee_id),
            ("assignment_id", "in", list(assignment_ids)),
            ("period", ">=", year_start),
            ("period", "<=", year_end),
        ]
        if hour_type:
            domain.append(("hour_type", "=", hour_type))

        groups = SyncEntry.read_group(domain, ["assignment_id", "hours:sum"], ["assignment_id"])
        return {g["assignment_id"][0]: g["hours"] for g in groups if g["assignment_id"]}

    @api.model
    def _pick_assignment_least_used(self, eligible_assignments, used_map):
        """Return the assignment with the fewest used leave hours (prefers 0)."""
        return min(
            eligible_assignments,
            key=lambda a: used_map.get(a.id, 0.0),
        )

    def _create_leave_internal_expense(self, leave, employee, period, hours, hour_type, source_assignment, note=""):
        """Create (or replace) a tenenet.internal.expense record for an uncovered leave."""
        InternalExpense = self.env["tenenet.internal.expense"].sudo()

        # Remove any existing record for this leave+period+employee (idempotent re-sync)
        InternalExpense.search([
            ("leave_id", "=", leave.id),
            ("period", "=", period),
            ("employee_id", "=", employee.id),
        ]).unlink()

        if source_assignment:
            wage_hm = source_assignment.wage_hm or 0.0
        elif employee.hourly_rate:
            wage_hm = employee.hourly_rate
        else:
            wage_hm = 0.0

        InternalExpense.create({
            "employee_id": employee.id,
            "period": period,
            "category": "leave",
            "leave_id": leave.id,
            "source_assignment_id": source_assignment.id if source_assignment else False,
            "hour_type": hour_type,
            "hours": hours,
            "wage_hm": wage_hm,
            "note": note,
        })

    # ── Preserved helpers (unchanged from original) ──────────────────────────

    def _ensure_tenenet_leave_mapping(self):
        """Validation guard: each approved leave must resolve to a TENENET leave category."""
        for leave in self:
            leave_type = leave.holiday_status_id
            if leave_type and not self._get_hour_type_for_leave(leave_type):
                raise ValidationError(
                    f"Typ dovolenky '{leave_type.display_name}' nemá mapovanie na TENENET kategóriu hodín. "
                    "Nastavte pole 'Tenenet typ hodín' na type dovolenky."
                )

    @api.model
    def _split_hours_evenly(self, total_hours, count):
        if count <= 0:
            return []
        rounded_total = round(total_hours, 2)
        base = round(rounded_total / count, 2)
        result = [base for _ in range(count)]
        delta = round(rounded_total - sum(result), 2)
        result[-1] = round(result[-1] + delta, 2)
        return result

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
        """Return number of leave hours falling in the given month."""
        self.ensure_one()
        total_hours = self._get_total_leave_hours()
        if total_hours <= 0.001:
            return 0.0

        if not self.date_from or not self.date_to:
            return total_hours

        date_from = self.date_from.date()
        date_to = self.date_to.date()
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

        total_days = (date_to - date_from).days + 1
        overlap_days = (overlap_end - overlap_start).days
        if total_days <= 0:
            return total_hours

        ratio = overlap_days / total_days
        return round(total_hours * ratio, 2)

    def _get_total_leave_hours(self):
        """Get total leave hours with number_of_hours as primary source."""
        self.ensure_one()
        hours = self.number_of_hours or 0.0
        if hours > 0.001:
            return round(hours, 2)

        days = self.number_of_days or 0.0
        if days <= 0.0:
            return 0.0

        hours_per_day = self._get_employee_hours_per_day()
        return round(days * hours_per_day, 2)

    def _get_employee_hours_per_day(self):
        employee = self.employee_id
        if not employee:
            return 8.0

        calendar = employee.resource_calendar_id
        if not calendar:
            return 8.0

        return calendar.hours_per_day or 8.0

    def _get_hour_type_for_leave(self, leave_type):
        """Get TENENET hour type for an hr.leave.type."""
        if hasattr(leave_type, "tenenet_hour_type") and leave_type.tenenet_hour_type:
            return leave_type.tenenet_hour_type
        return self._leave_type_to_hour_type_by_pattern(leave_type)

    @api.model
    def _leave_type_to_hour_type_by_pattern(self, leave_type):
        """Map an hr.leave.type to hour type using name/code patterns."""
        name_lower = (leave_type.name or "").lower()
        code_lower = (getattr(leave_type, "code", "") or "").lower()

        if any(k in name_lower or k in code_lower for k in (
            "dovolenk", "vacation", "annual", "svadba", "pohreb", "narodenie",
            "studijn", "nahradn"
        )):
            return "vacation"

        if any(k in name_lower or k in code_lower for k in (
            "pn", "ocr", "sick", "chorob", "matersk", "rodicovsk",
            "práceneschop", "osetrov"
        )):
            return "sick"

        if any(k in name_lower or k in code_lower for k in (
            "lekar", "lekár", "doctor", "medical", "spreva"
        )):
            return "doctor"

        if any(k in name_lower or k in code_lower for k in (
            "sviat", "holiday", "public", "platen"
        )):
            return "holidays"

        return None

    @api.model
    def _leave_type_to_field(self, leave_type):
        """Deprecated: kept for backward compatibility."""
        hour_type = self._get_hour_type_for_leave(leave_type)
        if not hour_type:
            return None
        return {
            "vacation": "hours_vacation",
            "sick": "hours_sick",
            "doctor": "hours_doctor",
            "holidays": "hours_holidays",
        }.get(hour_type)
