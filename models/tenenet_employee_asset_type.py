from odoo import fields, models


class TenenetEmployeeAssetType(models.Model):
    _name = "tenenet.employee.asset.type"
    _description = "Typ firemného majetku"
    _order = "name"

    _unique_name = models.Constraint(
        "UNIQUE(name)",
        "Typ firemného majetku už existuje.",
    )

    name = fields.Char(string="Typ majetku", required=True)
    active = fields.Boolean(string="Aktívne", default=True)
