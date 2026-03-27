"""
Migration 19.0.5.0.0 → 19.0.5.1.0

Converts the old internal-project-based cost tracking to the new
tenenet.internal.expense model:

1. Migrate tenenet.company.expense records → tenenet.internal.expense (category=leave)
2. Migrate leave sync entries that point to internal project assignments
   → tenenet.internal.expense (category=leave)
3. Zero out leave hours on internal project timesheets (they're migrated above)
4. Archive the internal project (do NOT delete — kept for audit trail)
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _migrate_company_expenses(env)
    _migrate_internal_sync_entries(env)
    _archive_internal_project(env)


def _migrate_company_expenses(env):
    """Convert tenenet.company.expense → tenenet.internal.expense (category=leave)."""
    CompanyExpense = env["tenenet.company.expense"]
    InternalExpense = env["tenenet.internal.expense"]

    expenses = CompanyExpense.search([])
    if not expenses:
        _logger.info("No tenenet.company.expense records to migrate.")
        return

    _logger.info("Migrating %d tenenet.company.expense records to tenenet.internal.expense.", len(expenses))

    # expense_type on company expense maps directly to hour_type
    HOUR_TYPE_MAP = {
        "vacation": "vacation",
        "sick": "sick",
        "doctor": "doctor",
        "holidays": "holidays",
    }

    migrated = 0
    skipped = 0
    for exp in expenses:
        # Check if already migrated (idempotent)
        if exp.leave_id:
            existing = InternalExpense.search([
                ("leave_id", "=", exp.leave_id.id),
                ("period", "=", exp.period),
                ("employee_id", "=", exp.employee_id.id),
                ("category", "=", "leave"),
            ], limit=1)
            if existing:
                skipped += 1
                continue

        try:
            InternalExpense.create({
                "employee_id": exp.employee_id.id,
                "period": exp.period,
                "category": "leave",
                "leave_id": exp.leave_id.id if exp.leave_id else False,
                "source_assignment_id": False,
                "hour_type": HOUR_TYPE_MAP.get(exp.expense_type),
                "hours": exp.hours or 0.0,
                "wage_hm": exp.hourly_rate_hm or 0.0,
                "note": (exp.note or "") + " [Migrované z tenenet.company.expense]",
            })
            migrated += 1
        except Exception as exc:
            _logger.warning(
                "Could not migrate company expense id=%s: %s", exp.id, exc
            )
            skipped += 1

    _logger.info(
        "company.expense migration: %d migrated, %d skipped.", migrated, skipped
    )


def _migrate_internal_sync_entries(env):
    """Migrate leave sync entries pointing to internal-project assignments."""
    SyncEntry = env["tenenet.project.leave.sync.entry"]
    InternalExpense = env["tenenet.internal.expense"]
    Timesheet = env["tenenet.project.timesheet"]

    # Find internal projects (including archived ones)
    internal_projects = env["tenenet.project"].with_context(active_test=False).search([
        ("is_tenenet_internal", "=", True),
    ])
    if not internal_projects:
        _logger.info("No internal project found — skipping sync entry migration.")
        return

    internal_assignments = env["tenenet.project.assignment"].with_context(active_test=False).search([
        ("project_id", "in", internal_projects.ids),
    ])
    if not internal_assignments:
        _logger.info("No internal project assignments found — skipping sync entry migration.")
        return

    internal_entries = SyncEntry.search([
        ("assignment_id", "in", internal_assignments.ids),
    ])
    _logger.info(
        "Migrating %d internal-project leave sync entries to tenenet.internal.expense.",
        len(internal_entries),
    )

    migrated = 0
    skipped = 0
    affected_assignment_periods = set()

    for entry in internal_entries:
        existing = InternalExpense.search([
            ("leave_id", "=", entry.leave_id.id),
            ("period", "=", entry.period),
            ("employee_id", "=", entry.employee_id.id),
            ("category", "=", "leave"),
        ], limit=1)
        if existing:
            skipped += 1
            affected_assignment_periods.add((entry.assignment_id.id, entry.period))
            continue

        try:
            InternalExpense.create({
                "employee_id": entry.employee_id.id,
                "period": entry.period,
                "category": "leave",
                "leave_id": entry.leave_id.id if entry.leave_id else False,
                "source_assignment_id": False,
                "hour_type": entry.hour_type,
                "hours": entry.hours or 0.0,
                "wage_hm": entry.assignment_id.wage_hm or 0.0,
                "note": "Migrované z interného projektu TENENET",
            })
            affected_assignment_periods.add((entry.assignment_id.id, entry.period))
            migrated += 1
        except Exception as exc:
            _logger.warning(
                "Could not migrate sync entry id=%s: %s", entry.id, exc
            )
            skipped += 1

    _logger.info(
        "Sync entry migration: %d migrated, %d skipped.", migrated, skipped
    )

    # Delete migrated sync entries so _rebuild_timesheets won't restore them
    internal_entries.unlink()

    # Zero out leave hours on affected internal project timesheets
    leave_hour_fields = ["hours_vacation", "hours_sick", "hours_doctor", "hours_holidays"]
    zeroed = 0
    for assignment_id, period in affected_assignment_periods:
        ts = Timesheet.search([
            ("assignment_id", "=", assignment_id),
            ("period", "=", period),
        ], limit=1)
        if ts:
            ts.with_context(from_hr_leave_sync=True).write(
                {f: 0.0 for f in leave_hour_fields}
            )
            zeroed += 1

    _logger.info("Zeroed leave hours on %d internal project timesheet(s).", zeroed)


def _archive_internal_project(env):
    """Soft-delete (archive) the internal project — keep it for audit trail."""
    internal_projects = env["tenenet.project"].with_context(active_test=False).search([
        ("is_tenenet_internal", "=", True),
        ("active", "=", True),
    ])
    if internal_projects:
        internal_projects.write({"active": False})
        _logger.info(
            "Archived %d internal TENENET project(s): %s",
            len(internal_projects),
            ", ".join(internal_projects.mapped("name")),
        )
    else:
        _logger.info("No active internal project to archive.")
