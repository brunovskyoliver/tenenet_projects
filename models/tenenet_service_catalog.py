from odoo import models, fields


class TenenetServiceCatalog(models.Model):
    _name = "tenenet.service.catalog"
    _description = "Katalóg služieb"
    _order = "name"

    name = fields.Char(string="Služba", required=True, index=True)
    active = fields.Boolean(string="Aktívne", default=True)

    _name_unique = models.Constraint(
        "UNIQUE(name)",
        "Služba už existuje.",
    )
