from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_tenenet_client = fields.Boolean(string="Klient")
    is_tenenet_partner = fields.Boolean(string="Partner")
    is_tenenet_employee_contact = fields.Boolean(
        string="Kontakt zamestnanca",
        compute="_compute_tenenet_contact_roles",
        store=True,
    )
    tenenet_contact_role_summary = fields.Char(
        string="TENENET roly",
        compute="_compute_tenenet_contact_roles",
        store=True,
    )

    @api.depends("is_tenenet_client", "is_tenenet_partner", "employee_ids")
    def _compute_tenenet_contact_roles(self):
        for rec in self:
            roles = []
            is_employee_contact = bool(rec.employee_ids)
            rec.is_tenenet_employee_contact = is_employee_contact
            if is_employee_contact:
                roles.append("Zamestnanec")
            if rec.is_tenenet_client:
                roles.append("Klient")
            if rec.is_tenenet_partner:
                roles.append("Partner")
            rec.tenenet_contact_role_summary = ", ".join(roles) if roles else False
