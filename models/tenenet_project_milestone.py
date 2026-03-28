from odoo import _, api, fields, models


class TenenetProjectMilestone(models.Model):
    _name = "tenenet.project.milestone"
    _description = "Míľnik projektu"
    _order = "date asc, sequence asc, id asc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Míľnik", required=True, tracking=True)
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
    )
    date = fields.Date(string="Dátum", required=True, tracking=True)
    note = fields.Text(string="Poznámka", tracking=True)
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "tenenet_milestone_attach_rel",
        "milestone_id",
        "attachment_id",
        string="Prílohy",
    )
    alert_rule_id = fields.Many2one(
        "tenenet.alert.rule",
        string="Pravidlo upozornenia",
        ondelete="set null",
        copy=False,
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        project_ids = [vals.get("project_id") for vals in vals_list if vals.get("project_id")]
        self.env["tenenet.project"].browse(project_ids)._check_milestone_manage_access()
        return super().create(vals_list)

    def write(self, vals):
        projects = self.mapped("project_id")
        if vals.get("project_id"):
            projects |= self.env["tenenet.project"].browse(vals["project_id"])
        projects._check_milestone_manage_access()
        res = super().write(vals)
        if "name" in vals or "project_id" in vals:
            for rec in self:
                if rec.alert_rule_id:
                    rec.alert_rule_id.sudo().write({
                        "name": "Míľnik: %s – %s" % (rec.name, rec.project_id.name or ""),
                    })
        return res

    def unlink(self):
        self.mapped("project_id")._check_milestone_manage_access()
        alert_rules = self.mapped("alert_rule_id")
        res = super().unlink()
        alert_rules.sudo().unlink()
        return res

    def action_open_edit_wizard(self):
        self.ensure_one()
        self.project_id._check_milestone_manage_access()
        return {
            "name": _("Upraviť míľnik"),
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.milestone.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_project_id": self.project_id.id,
                "default_milestone_id": self.id,
                "default_name": self.name,
                "default_date": self.date,
                "default_note": self.note,
            },
        }

    def _sync_alert_rule(self, partner_ids=None, lead_amount=1, lead_unit="month"):
        """Create or update the dedicated alert rule for this milestone."""
        self.ensure_one()
        if partner_ids is None:
            partner_ids = []

        # Filter to partners that have an email (required by alert rule constraint)
        if partner_ids:
            valid_partners = self.env["res.partner"].sudo().browse(partner_ids).filtered("email")
            partner_ids = valid_partners.ids

        allowed_model = self.env["tenenet.alert.allowed.model"].sudo().search(
            [("model_model", "=", "tenenet.project.milestone")], limit=1
        )
        if not allowed_model:
            return

        rule_name = "Míľnik: %s – %s" % (self.name, self.project_id.name or "")
        existing_rule = self.sudo().alert_rule_id

        if existing_rule:
            existing_rule.write({
                "name": rule_name,
                "recipient_partner_ids": [(6, 0, partner_ids)],
            })
            date_cond = existing_rule.condition_ids.filtered(
                lambda c: c.field_name == "date"
            )[:1]
            if date_cond:
                date_cond.write({
                    "relative_amount": lead_amount,
                    "relative_unit": lead_unit,
                })
        else:
            date_field = self.env["ir.model.fields"].sudo().search(
                [("model", "=", "tenenet.project.milestone"), ("name", "=", "date")], limit=1
            )
            id_field = self.env["ir.model.fields"].sudo().search(
                [("model", "=", "tenenet.project.milestone"), ("name", "=", "id")], limit=1
            )
            if not date_field:
                return

            condition_vals = [(0, 0, {
                "field_id": date_field.id,
                "value_mode": "relative",
                "operator": "within_next",
                "relative_amount": lead_amount,
                "relative_unit": lead_unit,
            })]
            if id_field:
                condition_vals.append((0, 0, {
                    "field_id": id_field.id,
                    "value_mode": "static",
                    "operator": "eq",
                    "value_integer": self.id,
                }))

            rule = self.env["tenenet.alert.rule"].sudo().create({
                "name": rule_name,
                "allowed_model_id": allowed_model.id,
                "recipient_partner_ids": [(6, 0, partner_ids)],
                "condition_ids": condition_vals,
            })
            # Write alert_rule_id directly via SQL-level sudo to avoid re-triggering
            # the write() access check with alert_rule_id (a non-sensitive internal field)
            self.env.cr.execute(
                "UPDATE tenenet_project_milestone SET alert_rule_id = %s WHERE id = %s",
                (rule.id, self.id),
            )
            self.invalidate_recordset(["alert_rule_id"])
