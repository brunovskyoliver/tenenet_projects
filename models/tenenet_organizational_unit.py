from odoo import fields, models


class TenenetOrganizationalUnit(models.Model):
    _name = "tenenet.organizational.unit"
    _description = "Organizačná zložka TENENET"
    _order = "name"

    name = fields.Char(string="Názov", required=True)
    code = fields.Char(string="Kód", required=True)
    active = fields.Boolean(string="Aktívne", default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "Kód organizačnej zložky musí byť jedinečný.")
