from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError


class TenenetProjectContactWizard(models.TransientModel):
    _name = "tenenet.project.contact.wizard"
    _description = "Sprievodca pridaním kontaktov k projektu"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        readonly=True,
    )
    available_contact_ids = fields.Many2many(
        "tenenet.project.contact",
        compute="_compute_available_contact_ids",
    )
    contact_ids = fields.Many2many(
        "tenenet.project.contact",
        "tenenet_project_contact_wizard_rel",
        "wizard_id",
        "contact_id",
        string="Dostupné kontakty",
    )

    @api.depends("project_id")
    def _compute_available_contact_ids(self):
        Contact = self.env["tenenet.project.contact"]
        for rec in self:
            if not rec.project_id:
                rec.available_contact_ids = False
                continue
            rec.available_contact_ids = Contact.search([
                ("id", "not in", rec.project_id.contact_ids.ids),
            ])

    def action_confirm(self):
        self.ensure_one()
        available_ids = set(self.available_contact_ids.ids)
        selected_ids = set(self.contact_ids.ids)
        if not selected_ids:
            raise ValidationError("Vyberte aspoň jeden kontakt.")
        if not selected_ids.issubset(available_ids):
            raise ValidationError("Môžete vybrať iba dostupné kontakty.")
        self.project_id.write({"contact_ids": [Command.link(contact_id) for contact_id in self.contact_ids.ids]})
        return {"type": "ir.actions.act_window_close"}
