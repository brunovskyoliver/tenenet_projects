from odoo import models


class SignRequest(models.Model):
    _inherit = "sign.request"

    def _sign(self):
        res = super()._sign()
        handover_ids = [
            request.reference_doc.id
            for request in self
            if request.reference_doc
            and request.reference_doc._name == "tenenet.employee.asset.handover"
        ]
        handovers = self.env["tenenet.employee.asset.handover"].browse(handover_ids)
        handovers._close_helpdesk_ticket_if_signed()
        return res
