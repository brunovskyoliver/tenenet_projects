from odoo import fields, models


class TenenetExpenseTypeConfigCategory(models.Model):
    _name = "tenenet.expense.type.config.category"
    _description = "Mapovanie TENENET typu na HR kategóriu výdavku"
    _order = "sequence, id"

    config_id = fields.Many2one(
        "tenenet.expense.type.config",
        string="TENENET typ výdavku",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="Poradie", default=10)
    product_id = fields.Many2one(
        "product.product",
        string="HR kategória výdavku",
        required=True,
        ondelete="restrict",
        domain=[("can_be_expensed", "=", True)],
    )
