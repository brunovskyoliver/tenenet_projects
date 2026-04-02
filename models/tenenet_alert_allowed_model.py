from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TenenetAlertAllowedModel(models.Model):
    _name = "tenenet.alert.allowed.model"
    _description = "Povolený model pre upozornenia"
    _order = "model_model"
    _rec_name = "model_label"

    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        required=True,
        ondelete="cascade",
        domain=[("transient", "=", False)],
    )
    model_label = fields.Char(
        string="Názov modelu",
        compute="_compute_model_label",
        search="_search_model_label",
        readonly=True,
        translate=False,
    )
    model_name = fields.Char(string="Názov modelu", related="model_id.name", store=True, readonly=True, translate=False)
    model_model = fields.Char(string="Technický názov", related="model_id.model", store=True, readonly=True)
    active = fields.Boolean(string="Aktívny", default=True)
    notes = fields.Text(string="Poznámky")
    rule_ids = fields.One2many("tenenet.alert.rule", "allowed_model_id", string="Pravidlá")

    _unique_model = models.Constraint(
        "UNIQUE(model_id)",
        "Každý model môže byť v zozname povolených modelov iba raz.",
    )

    @api.depends("model_id", "model_id.name")
    def _compute_model_label(self):
        for rec in self:
            rec.model_label = rec.model_id.name or False

    @api.model
    def _search_model_label(self, operator, value):
        return [("model_id.name", operator, value)]

    @api.model
    def _sync_default_allowed_models(self):
        defaults = [
            (
                "tenenet.project.assignment",
                "Priradenia zamestnancov k projektom – monitorovanie konca priradenia (date_end)",
            ),
            (
                "tenenet.project",
                "Projekty – monitorovanie termínov a stavu projektu",
            ),
            (
                "tenenet.project.milestone",
                "Míľniky projektov – monitorovanie termínov míľnikov podľa projektu",
            ),
        ]
        ir_model = self.env["ir.model"].sudo()
        for technical_name, notes in defaults:
            model = ir_model.search([("model", "=", technical_name)], limit=1)
            if not model:
                continue
            allowed_model = self.with_context(active_test=False).search([("model_id", "=", model.id)], limit=1)
            values = {
                "active": True,
                "notes": notes,
            }
            if allowed_model:
                allowed_model.write(values)
                continue
            self.create({
                "model_id": model.id,
                **values,
            })

    @api.constrains("model_id")
    def _check_model_id(self):
        blocked_models = {"res.config.settings"}
        blocked_prefixes = ("ir.", "mail.", "bus.")
        for rec in self:
            model = rec.model_id
            if not model:
                continue
            if model.transient:
                raise ValidationError("Pre upozornenia nie je možné povoliť dočasný model.")
            if getattr(model, "abstract", False):
                raise ValidationError("Pre upozornenia nie je možné povoliť abstraktný model.")
            if model.model in blocked_models or model.model.startswith(blocked_prefixes):
                raise ValidationError("Vybraný technický model nie je možné použiť pre upozornenia.")
