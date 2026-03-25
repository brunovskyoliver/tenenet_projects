from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if "lang" in fields_list and "lang" not in defaults:
            defaults["lang"] = "sk_SK"
        return defaults
