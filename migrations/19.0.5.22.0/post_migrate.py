from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["tenenet.expense.type.config"]._load_default_operating_seed_data()
