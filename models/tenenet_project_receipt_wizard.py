from odoo import fields, models


class TenenetProjectReceiptWizard(models.TransientModel):
    _name = "tenenet.project.receipt.wizard"
    _description = "Sprievodca pridaním príjmu projektu"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
    )
    date_received = fields.Date(
        string="Dátum prijatia",
        required=True,
        default=fields.Date.today,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="project_id.currency_id",
    )
    amount = fields.Monetary(
        string="Prijaté (€)",
        currency_field="currency_id",
        required=True,
    )
    note = fields.Char(string="Poznámka")

    def action_add(self):
        self.ensure_one()
        self.env["tenenet.project.receipt"].create({
            "project_id": self.project_id.id,
            "date_received": self.date_received,
            "amount": self.amount,
            "note": self.note or False,
        })
        return {"type": "ir.actions.client", "tag": "soft_reload"}
