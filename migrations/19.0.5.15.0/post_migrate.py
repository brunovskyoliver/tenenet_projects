from odoo import SUPERUSER_ID, api


CCP_MULTIPLIER = 1.362


def _column_exists(cr, table, column):
    cr.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = %s
              AND column_name = %s
        )
        """,
        (table, column),
    )
    return cr.fetchone()[0]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    if _column_exists(cr, "hr_employee", "monthly_gross_salary_target"):
        cr.execute(
            """
            UPDATE hr_employee
               SET monthly_gross_salary_target = monthly_gross_salary_target * %s
             WHERE monthly_gross_salary_target IS NOT NULL
               AND monthly_gross_salary_target != 0
            """,
            (CCP_MULTIPLIER,),
        )

    if _column_exists(cr, "hr_employee", "is_mgmt") and _column_exists(cr, "hr_job", "is_tenenet_admin_management"):
        cr.execute(
            """
            UPDATE hr_job job
               SET is_tenenet_admin_management = TRUE
              FROM hr_employee employee
             WHERE employee.job_id = job.id
               AND employee.is_mgmt IS TRUE
            """
        )

    if _column_exists(cr, "tenenet_employee_asset", "serial_number"):
        cr.execute(
            """
            UPDATE tenenet_employee_asset
               SET serial_number = 'NEEVIDOVANE-' || id::text
             WHERE serial_number IS NULL
                OR serial_number = ''
            """
        )

    if _column_exists(cr, "tenenet_employee_asset", "handover_date"):
        cr.execute(
            """
            UPDATE tenenet_employee_asset
               SET handover_date = COALESCE(create_date::date, CURRENT_DATE)
             WHERE handover_date IS NULL
            """
        )

    env["tenenet.employee.tenenet.cost"].search([])._sync_internal_residual_expense()
