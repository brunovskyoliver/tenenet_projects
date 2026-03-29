from odoo import api, fields, models


class TenenetExpenseTypeConfig(models.Model):
    _name = "tenenet.expense.type.config"
    _description = "Typ projektového nákladu (katalóg)"
    _order = "sequence, name"

    name = fields.Char(string="Názov typu nákladu", required=True)
    description = fields.Text(string="Popis")
    sequence = fields.Integer(string="Poradie", default=10)
    active = fields.Boolean(string="Aktívny", default=True)
    expense_category_line_ids = fields.One2many(
        "tenenet.expense.type.config.category",
        "config_id",
        string="Kategórie HR výdavkov",
    )
    hr_expense_product_id = fields.Many2one(
        "product.product",
        string="HR kategória výdavku",
        domain=[("can_be_expensed", "=", True)],
    )

    @api.onchange("hr_expense_product_id")
    def _onchange_hr_expense_product_id(self):
        for rec in self:
            rec._sync_primary_category_line()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_primary_category_line()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "hr_expense_product_id" in vals:
            self._sync_primary_category_line()
        return result

    def _get_primary_expense_category(self):
        self.ensure_one()
        if self.hr_expense_product_id:
            return self.hr_expense_product_id
        return self.expense_category_line_ids.sorted(
            key=lambda line: (line.sequence, line.id)
        ).mapped("product_id")[:1]

    def _sync_primary_category_line(self):
        for rec in self:
            primary_line = rec.expense_category_line_ids.sorted(
                key=lambda line: (line.sequence, line.id)
            )[:1]
            if rec.hr_expense_product_id:
                if primary_line:
                    primary_line.product_id = rec.hr_expense_product_id
                else:
                    rec.expense_category_line_ids = [(0, 0, {
                        "sequence": 10,
                        "product_id": rec.hr_expense_product_id.id,
                    })]
            elif primary_line:
                primary_line.unlink()
