from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["tenenet.project"].with_context(active_test=False).search([])._ensure_admin_tenenet_entities()
    services = env["tenenet.employee.service"].with_context(active_test=False).search([
        ("delivery_online", "=", False),
        ("delivery_in_person", "=", False),
    ])
    if services:
        services.write({
            "delivery_online": True,
            "delivery_in_person": True,
        })
