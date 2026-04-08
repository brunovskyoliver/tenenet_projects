from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _ensure_admin_tenenet_entities(env)
    _migrate_admin_override_rows(env)


def _ensure_admin_tenenet_entities(env):
    env["tenenet.project"]._ensure_admin_tenenet_entities()


def _migrate_admin_override_rows(env):
    override_model = env["tenenet.pl.program.override"].with_context(include_separators=True)
    legacy_rows = override_model.search([("row_key", "in", ["support_admin", "management"])])
    grouped = {}
    for row in legacy_rows:
        key = (row.program_id.id, row.period)
        grouped.setdefault(key, {
            "program_id": row.program_id.id,
            "period": row.period,
            "amount": 0.0,
            "is_manual": False,
            "note": [],
        })
        grouped[key]["amount"] += row.amount or 0.0
        grouped[key]["is_manual"] = grouped[key]["is_manual"] or row.is_manual
        if row.note:
            grouped[key]["note"].append(row.note)

    for values in grouped.values():
        target = override_model.search([
            ("program_id", "=", values["program_id"]),
            ("period", "=", values["period"]),
            ("row_key", "=", "admin_tenenet_cost"),
        ], limit=1)
        if target:
            target.with_context(_pl_program_override_syncing=True).write({
                "amount": values["amount"],
                "is_manual": values["is_manual"],
                "note": " | ".join(values["note"]),
            })
