from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["helpdesk.ticket"]._ensure_tenenet_internal_helpdesk_setup()
