from odoo import fields, models


class TenenetEmployeeAsset(models.Model):
    _name = "tenenet.employee.asset"
    _description = "Firemný majetok zamestnanca"
    _order = "employee_id, asset_type_id, id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
    )
    asset_type_id = fields.Many2one(
        "tenenet.employee.asset.type",
        string="Typ majetku",
        required=True,
        ondelete="restrict",
    )
    name = fields.Char(string="Majetok", related="asset_type_id.name", store=True, readonly=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
        required=True,
    )
    cost = fields.Monetary(
        string="Hodnota (€)",
        currency_field="currency_id",
        default=0.0,
        help="Voliteľná hodnota prideleného majetku pre zamestnanca.",
    )
    note = fields.Text(string="Poznámka")
    active = fields.Boolean(string="Aktívne", default=True)
