from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError


class TenenetProjectSite(models.Model):
    _name = "tenenet.project.site"
    _description = "Prevádzka / centrum / terén projektu"
    _order = "site_type, name"

    name = fields.Char(string="Názov", required=True)
    site_type = fields.Selection(
        [
            ("prevadzka", "Prevádzka"),
            ("centrum", "Centrum"),
            ("teren", "Terén"),
        ],
        string="Typ",
        required=True,
        default="prevadzka",
    )
    responsible_employee_id = fields.Many2one(
        "hr.employee",
        string="Zodpovedná osoba",
        ondelete="set null",
    )
    email = fields.Char(string="Email")
    phone = fields.Char(string="Telefón")
    street = fields.Char(string="Ulica")
    street2 = fields.Char(string="Ulica 2")
    zip = fields.Char(string="PSČ")
    city = fields.Char(string="Mesto")
    country_id = fields.Many2one("res.country", string="Krajina", ondelete="set null")
    landlord_partner_id = fields.Many2one(
        "res.partner",
        string="Prenajímateľ",
        ondelete="set null",
    )
    active = fields.Boolean(string="Aktívne", default=True)
    project_ids = fields.Many2many(
        "tenenet.project",
        "tenenet_project_site_rel",
        "site_id",
        "project_id",
        string="Priradené projekty",
        readonly=True,
    )
    contact_summary = fields.Char(string="Kontakt", compute="_compute_contact_summary")
    address_display = fields.Char(string="Adresa", compute="_compute_address_display")

    @api.depends("email", "phone", "responsible_employee_id.name")
    def _compute_contact_summary(self):
        for rec in self:
            parts = [value for value in [rec.responsible_employee_id.name, rec.email, rec.phone] if value]
            rec.contact_summary = " / ".join(parts) if parts else False

    @api.depends("street", "street2", "zip", "city", "country_id.name")
    def _compute_address_display(self):
        for rec in self:
            parts = [value for value in [rec.street, rec.street2] if value]
            city_line = " ".join(value for value in [rec.zip, rec.city] if value)
            if city_line:
                parts.append(city_line)
            if rec.country_id:
                parts.append(rec.country_id.name)
            rec.address_display = ", ".join(parts) if parts else False

    def action_unlink_from_project(self):
        self.ensure_one()
        project_id = self.env.context.get("unlink_project_id")
        if not project_id:
            raise ValidationError("Chýba projekt pre odpojenie prevádzky.")
        project = self.env["tenenet.project"].browse(project_id).exists()
        if not project:
            raise ValidationError("Projekt pre odpojenie prevádzky neexistuje.")
        project.write({"site_ids": [Command.unlink(self.id)]})
        return {"type": "ir.actions.client", "tag": "reload"}
