from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TenenetAlertAllowedModel(models.Model):
    _name = "tenenet.alert.allowed.model"
    _description = "Povolený model pre upozornenia"
    _order = "model_name"
    _rec_name = "model_name"

    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        required=True,
        ondelete="cascade",
        domain=[("transient", "=", False)],
    )
    model_name = fields.Char(string="Názov modelu", related="model_id.name", store=True, readonly=True)
    model_model = fields.Char(string="Technický názov", related="model_id.model", store=True, readonly=True)
    active = fields.Boolean(string="Aktívny", default=True)
    notes = fields.Text(string="Poznámky")
    rule_ids = fields.One2many("tenenet.alert.rule", "allowed_model_id", string="Pravidlá")

    _unique_model = models.Constraint(
        "UNIQUE(model_id)",
        "Každý model môže byť v zozname povolených modelov iba raz.",
    )

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
