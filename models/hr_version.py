from odoo import fields, models


class HrVersion(models.Model):
    _inherit = "hr.version"

    additional_note = fields.Text(
        string="Additional Note",
        groups="",
        tracking=True,
    )
