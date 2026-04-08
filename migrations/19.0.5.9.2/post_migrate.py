from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["tenenet.project"]._ensure_admin_tenenet_entities()
    env["tenenet.project.site"]._sync_slovak_regions()
