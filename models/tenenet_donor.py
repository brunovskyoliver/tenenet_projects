from odoo import api, fields, models


class TenenetDonor(models.Model):
    _name = "tenenet.donor"
    _description = "Donor TENENET"
    _order = "name"

    name = fields.Char(string="Názov donora", required=True)
    donor_type = fields.Selection(
        [
            ("sr_samosprava", "SR - samospráva"),
            ("sr_ministerstvo", "SR - ministerstvo"),
            ("eu", "EÚ"),
            ("international", "Medzinárodný"),
            ("private", "Súkromný"),
        ],
        string="Typ donora",
    )
    partner_id = fields.Many2one("res.partner", string="Partner", ondelete="restrict")
    contact_info = fields.Text(
        string="Kontaktné informácie",
        compute="_compute_contact_info",
        store=True,
    )
    active = fields.Boolean(string="Aktívny", default=True)
    project_ids = fields.One2many("tenenet.project", "donor_id", string="Projekty")

    @api.depends(
        "partner_id",
        "partner_id.name",
        "partner_id.email",
        "partner_id.phone",
        "partner_id.street",
        "partner_id.street2",
        "partner_id.zip",
        "partner_id.city",
        "partner_id.country_id.name",
        "partner_id.website",
    )
    def _compute_contact_info(self):
        for rec in self:
            rec.contact_info = rec._format_partner_contact(rec.partner_id)

    @api.model
    def _format_partner_contact(self, partner):
        if not partner:
            return False

        lines = []
        if partner.name:
            lines.append(partner.name)
        if partner.email:
            lines.append(partner.email)

        phones = [value for value in [partner.phone] if value]
        if phones:
            lines.append(" / ".join(dict.fromkeys(phones)))

        address_parts = [value for value in [partner.street, partner.street2] if value]
        city_line = " ".join(value for value in [partner.zip, partner.city] if value)
        if city_line:
            address_parts.append(city_line)
        if partner.country_id:
            address_parts.append(partner.country_id.name)
        if address_parts:
            lines.append(", ".join(address_parts))

        if partner.website:
            lines.append(partner.website)

        return "\n".join(lines) if lines else False
