from odoo import fields, models


class TenenetAlertMatch(models.Model):
    _name = "tenenet.alert.match"
    _description = "Zhoda upozornenia"
    _order = "last_seen_at desc, id desc"

    rule_id = fields.Many2one(
        "tenenet.alert.rule",
        string="Pravidlo",
        required=True,
        ondelete="cascade",
    )
    res_model = fields.Char(string="Model", required=True, index=True)
    res_id = fields.Integer(string="ID záznamu", required=True, index=True)
    is_active = fields.Boolean(string="Aktívna zhoda", default=True, index=True)
    first_matched_at = fields.Datetime(string="Prvá zhoda", required=True)
    last_seen_at = fields.Datetime(string="Naposledy zhoda", required=True)
    last_notified_at = fields.Datetime(string="Naposledy odoslané")
    last_display_name = fields.Char(string="Naposledy názov záznamu")
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        compute="_compute_project_id",
    )
    project_name = fields.Char(
        string="Názov projektu",
        compute="_compute_project_id",
    )

    _unique_rule_record = models.Constraint(
        "UNIQUE(rule_id, res_model, res_id)",
        "Pre jedno pravidlo môže existovať len jedna zhoda na rovnaký záznam.",
    )

    def _compute_project_id(self):
        project_model = self.env["tenenet.project"]
        for rec in self:
            project = project_model
            if rec.res_model and rec.res_id:
                target = self.env[rec.res_model].browse(rec.res_id).exists()
                if target:
                    if target._name == "tenenet.project":
                        project = target
                    elif "project_id" in target._fields:
                        candidate = target.project_id
                        if candidate and candidate._name == "tenenet.project":
                            project = candidate
            rec.project_id = project
            rec.project_name = project.display_name or False
