import re
import unicodedata

from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import email_normalize


NON_DIGIT_RE = re.compile(r"\D+")
SLOVAK_REGION_VARIANTS = [
    ("Bratislavský", "BSK", "Bratislavský samosprávny kraj"),
    ("Trnavský", "TSK", "Trnavský samosprávny kraj"),
    ("Trenčiansky", None, "Trenčiansky samosprávny kraj"),
    ("Nitriansky", "NSK", "Nitriansky samosprávny kraj"),
    ("Žilinský", "ŽSK", "Žilinský samosprávny kraj"),
    ("Banskobystrický", "BBSK", "Banskobystrický samosprávny kraj"),
    ("Prešovský", "PSK", "Prešovský samosprávny kraj"),
    ("Košický", "KSK", "Košický samosprávny kraj"),
]
SLOVAK_REGION_SELECTION = [(full_label, full_label) for _short_label, _code, full_label in SLOVAK_REGION_VARIANTS]
SLOVAK_REGION_VALUES = {value for value, _label in SLOVAK_REGION_SELECTION}


def _fold_region_key(value):
    text = " ".join((value or "").replace("\xa0", " ").split())
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold()


SLOVAK_REGION_ALIASES = {}
for short_label, code, full_label in SLOVAK_REGION_VARIANTS:
    SLOVAK_REGION_ALIASES[_fold_region_key(short_label)] = full_label
    SLOVAK_REGION_ALIASES[_fold_region_key(full_label)] = full_label
    if code:
        SLOVAK_REGION_ALIASES[_fold_region_key(code)] = full_label


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
    kraj = fields.Selection(
        SLOVAK_REGION_SELECTION,
        string="Kraj",
    )
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
    program_ids = fields.Many2many(
        "tenenet.program",
        "tenenet_project_site_program_rel",
        "site_id",
        "program_id",
        string="Programy",
    )
    legacy_program_text = fields.Text(string="Pôvodný text programov")
    site_key_ids = fields.One2many(
        "tenenet.employee.site.key",
        "site_id",
        string="Držitelia kľúčov",
    )
    contact_summary = fields.Char(string="Kontakt", compute="_compute_contact_summary")
    address_display = fields.Char(string="Adresa", compute="_compute_address_display")

    @api.constrains("email", "phone")
    def _check_contact_details(self):
        for rec in self:
            if rec.email and not email_normalize(rec.email):
                raise ValidationError("E-mail prevádzky nemá platný formát.")
            if rec.phone:
                rec._format_slovak_phone(rec.phone)

    @api.constrains("site_type", "name", "kraj")
    def _check_terrain_name(self):
        for rec in self:
            if rec.site_type == "teren" and rec.name not in SLOVAK_REGION_VALUES:
                raise ValidationError("Terén môže obsahovať iba jeden z definovaných krajov Slovenska.")
            if rec.site_type == "teren" and rec.kraj != rec.name:
                raise ValidationError("Terén musí mať zhodne nastavený názov aj kraj.")

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

    @api.onchange("site_type", "name")
    def _onchange_terrain_defaults(self):
        for rec in self:
            if rec.site_type == "teren":
                region_label = self._normalize_region_label(rec.name or rec.kraj)
                if region_label:
                    rec.name = region_label
                    rec.kraj = region_label
            elif rec.kraj:
                rec.kraj = self._normalize_region_label(rec.kraj) or rec.kraj

    @staticmethod
    def _normalize_region_label(value):
        if not value:
            return False
        return SLOVAK_REGION_ALIASES.get(_fold_region_key(value))

    @api.model
    def _sync_slovak_regions(self):
        all_sites = self.with_context(active_test=False).search([])
        for site in all_sites:
            region_label = self._normalize_region_label(site.name if site.site_type == "teren" else site.kraj)
            if site.site_type == "teren":
                if not region_label:
                    continue
                updates = {}
                if site.name != region_label:
                    updates["name"] = region_label
                if site.kraj != region_label:
                    updates["kraj"] = region_label
                if updates:
                    site.write(updates)
                continue
            if region_label and site.kraj != region_label:
                site.write({"kraj": region_label})

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

    @classmethod
    def _normalize_terrain_vals(cls, vals, record=None):
        normalized = dict(vals)
        site_type = normalized.get("site_type", record.site_type if record else False)
        name = normalized.get("name", record.name if record else False)
        kraj = normalized.get("kraj", record.kraj if record else False)
        if site_type == "teren":
            region_label = cls._normalize_region_label(name or kraj)
            if region_label:
                normalized["name"] = region_label
                normalized["kraj"] = region_label
        elif "kraj" in normalized:
            normalized["kraj"] = cls._normalize_region_label(normalized["kraj"]) or False
        return normalized

    @classmethod
    def _format_slovak_phone(cls, raw_phone):
        cleaned = (raw_phone or "").strip()
        if not cleaned:
            return False

        normalized = cleaned.replace("00", "+", 1) if cleaned.startswith("00") else cleaned
        if normalized.startswith("+"):
            digits = "+" + NON_DIGIT_RE.sub("", normalized[1:])
        else:
            digits = NON_DIGIT_RE.sub("", normalized)
            if digits.startswith("0"):
                digits = "421" + digits[1:]
            elif not digits.startswith("421"):
                raise ValidationError("Telefón musí byť slovenské číslo vo formáte 09xx..., 0xx/... alebo +421...")
            digits = "+" + digits

        national = digits[1:]
        if not national.startswith("421") or len(national) != 12:
            raise ValidationError("Telefón musí byť platné slovenské číslo.")

        rest = national[3:]
        if rest.startswith("9"):
            return f"+421 {rest[:3]} {rest[3:6]} {rest[6:]}"
        if rest.startswith("2"):
            return f"+421 2 {rest[1:5]} {rest[5:]}"
        return f"+421 {rest[:2]} {rest[2:5]} {rest[5:]}"

    @classmethod
    def _normalize_contact_vals(cls, vals):
        normalized = dict(vals)
        if "email" in normalized:
            normalized["email"] = email_normalize(normalized["email"]) or False
            if vals.get("email") and not normalized["email"]:
                raise ValidationError("E-mail prevádzky nemá platný formát.")
        if "phone" in normalized:
            normalized["phone"] = cls._format_slovak_phone(normalized["phone"]) if normalized["phone"] else False
        return normalized

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [
            self._normalize_contact_vals(self._normalize_terrain_vals(vals))
            for vals in vals_list
        ]
        return super().create(vals_list)

    def write(self, vals):
        for rec in self:
            normalized_vals = self._normalize_contact_vals(self._normalize_terrain_vals(vals, record=rec))
            super(TenenetProjectSite, rec).write(normalized_vals)
        return True
