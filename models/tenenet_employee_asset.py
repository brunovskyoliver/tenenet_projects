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
    serial_number = fields.Char(
        string="Výrobné číslo",
        required=True,
    )
    handover_date = fields.Date(
        string="Termín odovzdania",
        required=True,
        default=fields.Date.context_today,
    )
    handover_id = fields.Many2one(
        "tenenet.employee.asset.handover",
        string="Preberací protokol",
        ondelete="set null",
        index=True,
        copy=False,
    )
    sign_request_id = fields.Many2one(
        "sign.request",
        string="Podpisová žiadosť",
        related="handover_id.sign_request_id",
        readonly=True,
        store=True,
    )
    sign_state = fields.Selection(
        related="handover_id.sign_state",
        string="Stav podpisu",
        readonly=True,
        store=True,
    )
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
