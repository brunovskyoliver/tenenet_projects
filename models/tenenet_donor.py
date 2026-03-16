from odoo import fields, models


class TenenetDonor(models.Model):
    _name = "tenenet.donor"
    _description = "Donor TENENET"
    _order = "name"

    name = fields.Char(string="Názov donora", required=True)
    donor_type = fields.Selection(
        [
            ("sr_samosprava", "SR - samospráva"),
            ("sr_ministerstvo", "SR - ministerstvo"),
            ("eu", "EÚ"),
            ("international", "Medzinárodný"),
            ("private", "Súkromný"),
        ],
        string="Typ donora",
    )
    contact_info = fields.Text(string="Kontaktné informácie")
    active = fields.Boolean(string="Aktívny", default=True)
    project_ids = fields.One2many("tenenet.project", "donor_id", string="Projekty")
