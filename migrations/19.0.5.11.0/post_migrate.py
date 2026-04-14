from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    projects = env["tenenet.project"].with_context(active_test=False).search([
        ("is_tenenet_internal", "=", False),
        ("project_type", "=", False),
    ])
    if projects:
        projects.write({"project_type": "narodny"})
    env["tenenet.project"].with_context(active_test=False).search([])._ensure_admin_tenenet_entities()
