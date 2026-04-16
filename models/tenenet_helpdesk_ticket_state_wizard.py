from odoo import _, api, fields, models
from odoo.fields import Command
from odoo.exceptions import UserError


class TenenetHelpdeskTicketStateWizard(models.TransientModel):
    _name = "tenenet.helpdesk.ticket.state.wizard"
    _description = "TENENET Helpdesk Follow-up / Control Wizard"

    ticket_id = fields.Many2one(
        "helpdesk.ticket",
        string="Požiadavka",
        required=True,
        readonly=True,
    )
    request_type = fields.Selection(
        [
            ("followup", "Vyžiadať follow-up"),
            ("control", "Vyžiadať kontrolu"),
        ],
        string="Akcia",
        required=True,
        readonly=True,
    )
    allowed_user_ids = fields.Many2many(
        "res.users",
        compute="_compute_allowed_user_ids",
        export_string_translation=False,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Používateľ",
        required=True,
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        ticket_id = values.get("ticket_id") or self.env.context.get("default_ticket_id") or self.env.context.get("active_id")
        if not ticket_id:
            raise UserError(_("Nepodarilo sa určiť helpdesk požiadavku."))
        ticket = self.env["helpdesk.ticket"].browse(ticket_id)
        if not ticket or not ticket.exists():
            raise UserError(_("Vybraná helpdesk požiadavka neexistuje."))
        values["ticket_id"] = ticket.id
        values.setdefault("request_type", self.env.context.get("default_request_type"))
        return values

    @api.depends("ticket_id", "ticket_id.tenenet_assignment_domain_user_ids")
    def _compute_allowed_user_ids(self):
        for wizard in self:
            wizard.allowed_user_ids = [Command.set(wizard.ticket_id.tenenet_assignment_domain_user_ids.ids)]

    def action_confirm(self):
        self.ensure_one()
        if self.request_type == "followup":
            self.ticket_id.action_tenenet_request_followup(self.user_id)
        else:
            self.ticket_id.action_tenenet_request_control(self.user_id)
        return {"type": "ir.actions.act_window_close"}
