from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError


class TenenetProjectSiteWizard(models.TransientModel):
    _name = "tenenet.project.site.wizard"
    _description = "Sprievodca pridaním prevádzok, centier a terénu k projektu"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        readonly=True,
    )
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
    available_site_ids = fields.Many2many(
        "tenenet.project.site",
        compute="_compute_available_site_ids",
    )
    site_ids = fields.Many2many(
        "tenenet.project.site",
        "tenenet_project_site_wizard_rel",
        "wizard_id",
        "site_id",
        string="Dostupné možnosti",
    )

    @api.depends("project_id", "site_type")
    def _compute_available_site_ids(self):
        Site = self.env["tenenet.project.site"]
        for rec in self:
            if not rec.project_id or not rec.site_type:
                rec.available_site_ids = False
                continue
            rec.available_site_ids = Site.search([
                ("site_type", "=", rec.site_type),
                ("id", "not in", rec.project_id.site_ids.ids),
            ])

    @api.onchange("site_type")
    def _onchange_site_type(self):
        self.site_ids = [Command.clear()]

    def action_confirm(self):
        self.ensure_one()
        available_ids = set(self.available_site_ids.ids)
        selected_ids = set(self.site_ids.ids)
        if not selected_ids:
            raise ValidationError("Vyberte aspoň jednu prevádzku, centrum alebo terén.")
        if not selected_ids.issubset(available_ids):
            raise ValidationError("Môžete vybrať iba dostupné záznamy pre zvolený typ.")
        self.project_id.write({"site_ids": [Command.link(site_id) for site_id in self.site_ids.ids]})
        return {"type": "ir.actions.act_window_close"}
