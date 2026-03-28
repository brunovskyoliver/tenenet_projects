from odoo import fields, models


class TenenetExpenseTypeConfig(models.Model):
    _name = "tenenet.expense.type.config"
    _description = "Typ projektového nákladu (katalóg)"
    _order = "sequence, name"

    name = fields.Char(string="Názov typu nákladu", required=True)
    description = fields.Text(string="Popis")
    sequence = fields.Integer(string="Poradie", default=10)
    active = fields.Boolean(string="Aktívny", default=True)
