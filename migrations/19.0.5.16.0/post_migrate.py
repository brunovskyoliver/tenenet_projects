from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["tenenet.program"]._sync_organizational_units(force=True)
    env["hr.employee"]._backfill_organizational_units(force=True)
