import datetime

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TenenetProjectCashflowDistributeWizard(models.TransientModel):
    _name = "tenenet.project.cashflow.distribute.wizard"
    _description = "Sprievodca distribúciou cashflow príjmu"

    receipt_id = fields.Many2one(
        "tenenet.project.receipt",
        string="Príjem",
        required=True,
    )
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        related="receipt_id.project_id",
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="receipt_id.currency_id",
        readonly=True,
    )
    amount = fields.Monetary(
        string="Suma na distribúciu",
        currency_field="currency_id",
        required=True,
        default=lambda self: self._default_amount(),
    )
    date_from = fields.Date(
        string="Od",
        required=True,
        default=lambda self: self._default_date_from(),
    )
    date_to = fields.Date(
        string="Do",
        required=True,
        default=lambda self: self._default_date_to(),
    )

    @api.model
    def _get_default_receipt(self):
        receipt_id = self.env.context.get("default_receipt_id")
        if receipt_id:
            return self.env["tenenet.project.receipt"].browse(receipt_id).exists()
        return self.env["tenenet.project.receipt"]

    @api.model
    def _default_amount(self):
        receipt = self._get_default_receipt()
        return receipt.amount or 0.0

    @api.model
    def _default_date_from(self):
        receipt = self._get_default_receipt()
        if not receipt:
            return fields.Date.context_today(self)
        first_cashflow = receipt.cashflow_ids.sorted("date_start")[:1]
        return first_cashflow.date_start or receipt.date_received

    @api.model
    def _default_date_to(self):
        receipt = self._get_default_receipt()
        if not receipt or not receipt.year:
            return fields.Date.context_today(self)
        if receipt.cashflow_ids:
            return receipt.cashflow_ids.sorted("date_stop")[-1].date_stop
        return datetime.date(receipt.year, 12, 31)

    @api.constrains("date_from", "date_to", "receipt_id")
    def _check_dates(self):
        for rec in self:
            if not rec.receipt_id or not rec.date_from or not rec.date_to:
                continue
            if rec.date_from > rec.date_to:
                raise ValidationError("Dátum od nemôže byť neskôr ako dátum do.")
            if rec.date_from.year != rec.receipt_id.year or rec.date_to.year != rec.receipt_id.year:
                raise ValidationError("Distribúcia cashflow musí zostať v roku príjmu.")

    def action_distribute(self):
        self.ensure_one()
        self.receipt_id.distribute_cashflow_span(self.date_from, self.date_to, amount=self.amount)
        return {"type": "ir.actions.client", "tag": "soft_reload"}
