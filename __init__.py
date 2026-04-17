from . import controllers
from . import models


def post_init_hook(env):
    env["resource.calendar.leaves"]._import_sk_public_holidays()
    env["tenenet.project.site"]._sync_slovak_regions()
    _ensure_admin_tenenet_entities(env)
    env["tenenet.program"]._sync_organizational_units(force=True)
    env["hr.employee"]._backfill_organizational_units(force=True)
    env["helpdesk.ticket"]._ensure_tenenet_internal_helpdesk_setup()
    env["tenenet.onboarding"]._ensure_onboarding_helpdesk_stage()


def pre_init_hook(env):
    env.cr.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = 'tenenet_project'
        )
        """
    )
    table_exists = env.cr.fetchone()[0]
    if not table_exists:
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


def _ensure_admin_tenenet_entities(env):
    env["tenenet.project"]._ensure_admin_tenenet_entities()
