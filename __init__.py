from . import controllers
from . import models


def _table_exists(env, table_name):
    env.cr.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = %s
        )
        """,
        [table_name],
    )
    return env.cr.fetchone()[0]


def _ensure_alert_allowed_model_xmlids(env):
    if not _table_exists(env, "tenenet_alert_allowed_model"):
        return

    xmlid_map = {
        "alert_allowed_model_assignment": "tenenet.project.assignment",
        "alert_allowed_model_project": "tenenet.project",
    }
    for xmlid_name, model_name in xmlid_map.items():
        env.cr.execute(
            """
            SELECT aam.id
            FROM tenenet_alert_allowed_model AS aam
            JOIN ir_model AS im ON im.id = aam.model_id
            WHERE im.model = %s
            LIMIT 1
            """,
            [model_name],
        )
        row = env.cr.fetchone()
        if not row:
            continue
        allowed_model_id = row[0]
        env.cr.execute(
            """
            SELECT id
            FROM ir_model_data
            WHERE module = %s
              AND name = %s
              AND model = %s
            LIMIT 1
            """,
            ["tenenet_projects", xmlid_name, "tenenet.alert.allowed.model"],
        )
        xmlid_row = env.cr.fetchone()
        if xmlid_row:
            env.cr.execute(
                """
                UPDATE ir_model_data
                SET res_id = %s,
                    noupdate = %s
                WHERE id = %s
                """,
                [allowed_model_id, True, xmlid_row[0]],
            )
            continue
        env.cr.execute(
            """
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                "tenenet_projects",
                xmlid_name,
                "tenenet.alert.allowed.model",
                allowed_model_id,
                True,
            ],
        )


def post_init_hook(env):
    env["resource.calendar.leaves"]._import_sk_public_holidays()


def pre_init_hook(env):
    if not _table_exists(env, "tenenet_project"):
        return

    env.cr.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'tenenet_project'
              AND column_name = 'program_director_id'
        )
        """
    )
    legacy_column_exists = env.cr.fetchone()[0]
    if legacy_column_exists:
        env.cr.execute(
            "ALTER TABLE tenenet_project RENAME COLUMN program_director_id TO odborny_garant_id"
        )

    env.cr.execute("ALTER TABLE tenenet_project DROP COLUMN IF EXISTS financial_manager_id")
    _ensure_alert_allowed_model_xmlids(env)
