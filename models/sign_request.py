from odoo import models


class SignRequest(models.Model):
    _inherit = "sign.request"

    def _sign(self):
        res = super()._sign()
        handovers = self.filtered(
            lambda request: request.reference_doc
            and request.reference_doc._name == "tenenet.employee.asset.handover"
        ).mapped("reference_doc")
        handovers._close_helpdesk_ticket_if_signed()
        return res
