from odoo import api, fields, models

from .tenenet_project_timesheet import HOUR_FIELD_BY_TYPE, HOUR_FIELD_META


LEAVE_HOUR_TYPES = tuple(
    meta["type"] for meta in HOUR_FIELD_META.values() if meta["scope"] == "leave"
)
LEAVE_HOUR_FIELDS = tuple(
    field_name for field_name, meta in HOUR_FIELD_META.items() if meta["scope"] == "leave"
)


class TenenetProjectLeaveSyncEntry(models.Model):
    _name = "tenenet.project.leave.sync.entry"
    _description = "Leave sync ledger for TENENET timesheets"
    _order = "period desc, employee_id, leave_id, assignment_id, hour_type"

    leave_id = fields.Many2one(
        "hr.leave",
        string="Dovolenka",
        required=True,
        ondelete="cascade",
        index=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
        index=True,
    )
    assignment_id = fields.Many2one(
        "tenenet.project.assignment",
        string="Priradenie",
        required=True,
        ondelete="cascade",
        index=True,
    )
    period = fields.Date(
        string="Obdobie",
        required=True,
        help="Prvý deň mesiaca",
        index=True,
    )
    hour_type = fields.Selection(
        selection=[(hour_type, hour_type) for hour_type in LEAVE_HOUR_TYPES],
        string="Typ hodín",
        required=True,
        index=True,
    )
    hours = fields.Float(
        string="Hodiny",
        required=True,
        digits=(10, 2),
        default=0.0,
    )

    _unique_leave_assignment_period_type = models.Constraint(
        "UNIQUE(leave_id, assignment_id, period, hour_type)",
        "Pre dovolenku môže existovať len jeden sync riadok pre priradenie/mesiac/typ.",
    )

    @api.model
    def _replace_for_leave(self, leave, allocations):
        ledger = self.sudo()
        existing = ledger.search([("leave_id", "=", leave.id)])
        affected_keys = {
            (row.assignment_id.id, row.period)
            for row in existing
            if row.assignment_id and row.period
        }
        if existing:
            existing.unlink()

        create_vals = []
        for allocation in allocations:
            hours = allocation.get("hours") or 0.0
            if hours <= 0.001:
                continue
            period = allocation["period"].replace(day=1)
            create_vals.append({
                "leave_id": leave.id,
                "employee_id": leave.employee_id.id,
                "assignment_id": allocation["assignment_id"],
                "period": period,
                "hour_type": allocation["hour_type"],
                "hours": round(hours, 2),
            })
            affected_keys.add((allocation["assignment_id"], period))

        if create_vals:
            ledger.create(create_vals)
        if affected_keys:
            ledger._rebuild_timesheets(affected_keys)

    @api.model
    def _rebuild_timesheets(self, affected_keys):
        Timesheet = self.env["tenenet.project.timesheet"].sudo().with_context(from_hr_leave_sync=True)
        Assignment = self.env["tenenet.project.assignment"].sudo()
        Matrix = self.env["tenenet.project.timesheet.matrix"].sudo()
        leave_fields = {field_name: 0.0 for field_name in LEAVE_HOUR_FIELDS}

        for assignment_id, period in sorted(affected_keys, key=lambda item: (item[1], item[0])):
            assignment = Assignment.browse(assignment_id).exists()
            if not assignment:
                continue

            timesheet = Timesheet._get_or_create_for_assignment_period(assignment, period)
            entries = self.sudo().search([
                ("assignment_id", "=", assignment.id),
                ("period", "=", period),
            ])

            vals = dict(leave_fields)
            for row in entries:
                field_name = HOUR_FIELD_BY_TYPE.get(row.hour_type)
                if field_name in vals:
                    vals[field_name] += row.hours or 0.0
            vals["leave_auto_synced"] = bool(entries)

            timesheet.write(vals)

        if affected_keys:
            Matrix._refresh_for_assignment_periods(affected_keys)
