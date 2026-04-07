from odoo import api, fields, models


class TenenetProjectAllowedExpenseTypeWizard(models.TransientModel):
    _name = "tenenet.project.allowed.expense.type.wizard"
    _description = "Sprievodca pridaním povoleného typu výdavku"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
    )
    config_id = fields.Many2one(
        "tenenet.expense.type.config",
        string="Typ nákladu (z katalógu)",
        ondelete="set null",
    )
    name = fields.Char(string="Názov", required=True)
    description = fields.Text(string="Popis")
    currency_id = fields.Many2one(
        "res.currency",
        related="project_id.currency_id",
    )
    max_amount = fields.Monetary(
        string="Max. povolená suma na projekt",
        currency_field="currency_id",
        default=0.0,
        help="0 = bez limitu",
    )

    @api.onchange("config_id")
    def _onchange_config_id(self):
        if self.config_id:
            self.name = self.config_id.name
            self.description = self.config_id.description or False

    def action_add(self):
        self.ensure_one()
        self.env["tenenet.project.allowed.expense.type"].create({
            "project_id": self.project_id.id,
            "config_id": self.config_id.id,
            "name": self.name,
            "description": self.description or False,
            "max_amount": self.max_amount,
        })
        return {"type": "ir.actions.act_window_close"}
