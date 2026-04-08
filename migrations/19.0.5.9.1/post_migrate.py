from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["tenenet.project"]._ensure_admin_tenenet_entities()
    _clear_legacy_program_metric_columns(cr)


def _clear_legacy_program_metric_columns(cr):
    for column in ("headcount", "reporting_fte", "operating_allocation_pct"):
        cr.execute(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = 'tenenet_program'
               AND column_name = %s
            """,
            [column],
        )
        if cr.fetchone():
            cr.execute(f"UPDATE tenenet_program SET {column} = NULL")
