from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import email_normalize

from .tenenet_project_site import TenenetProjectSite


class TenenetProjectContact(models.Model):
    _name = "tenenet.project.contact"
    _description = "Kontakt projektu"
    _order = "name"

    name = fields.Char(string="Názov", required=True)
    email = fields.Char(string="Email")
    phone = fields.Char(string="Telefón")
    note = fields.Text(string="Poznámka")
    website = fields.Char(string="Webstránka")
    active = fields.Boolean(string="Aktívny", default=True)
    project_ids = fields.Many2many(
        "tenenet.project",
        "tenenet_project_contact_rel",
        "contact_id",
        "project_id",
        string="Priradené projekty",
        readonly=True,
    )

    @api.constrains("email", "phone")
    def _check_contact_details(self):
        for rec in self:
            if rec.email and not email_normalize(rec.email):
                raise ValidationError("E-mail kontaktu nemá platný formát.")
            if rec.phone:
                TenenetProjectSite._format_slovak_phone(rec.phone)

    @classmethod
    def _normalize_contact_vals(cls, vals):
        normalized = dict(vals)
        if "email" in normalized:
            normalized["email"] = email_normalize(normalized["email"]) or False
            if vals.get("email") and not normalized["email"]:
                raise ValidationError("E-mail kontaktu nemá platný formát.")
        if "phone" in normalized:
            normalized["phone"] = (
                TenenetProjectSite._format_slovak_phone(normalized["phone"])
                if normalized["phone"]
                else False
            )
        if "website" in normalized:
            normalized["website"] = (normalized["website"] or "").strip() or False
        return normalized

    def action_unlink_from_project(self):
        self.ensure_one()
        project_id = self.env.context.get("unlink_project_id")
        if not project_id:
            raise ValidationError("Chýba projekt pre odpojenie kontaktu.")
        project = self.env["tenenet.project"].browse(project_id).exists()
        if not project:
            raise ValidationError("Projekt pre odpojenie kontaktu neexistuje.")
        project.write({"contact_ids": [Command.unlink(self.id)]})
        return {"type": "ir.actions.client", "tag": "reload"}

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._normalize_contact_vals(vals) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        vals = self._normalize_contact_vals(vals)
        return super().write(vals)
