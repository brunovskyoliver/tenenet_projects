from odoo import _, models
from odoo.exceptions import UserError


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    def write(self, vals):
        if "stage_id" in vals and not self.env.context.get("allow_handover_stage_write"):
            target_stage_id = vals.get("stage_id")
            tickets_with_manual_stage_change = self.filtered(
                lambda ticket: ticket.stage_id.id != target_stage_id
            )
            if tickets_with_manual_stage_change:
                locked_handover_tickets = self.env["tenenet.employee.asset.handover"].sudo().search([
                    ("helpdesk_ticket_id", "in", tickets_with_manual_stage_change.ids),
                ])
                if locked_handover_tickets:
                    raise UserError(_(
                        "Stav helpdesk požiadavky pre preberací protokol nie je možné meniť ručne. "
                        "Požiadavka sa uzatvorí automaticky po podpise dokumentu."
                    ))
        return super().write(vals)
