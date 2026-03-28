from odoo import fields, models


class TenenetProjectAllowedExpenseType(models.Model):
    _name = "tenenet.project.allowed.expense.type"
    _description = "Povolený typ výdavku projektu"
    _order = "project_id, name"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(string="Typ výdavku", required=True)
    description = fields.Text(string="Popis")
