from odoo import api, fields, models


class TenenetProjectMilestoneWizard(models.TransientModel):
    _name = "tenenet.project.milestone.wizard"
    _description = "Sprievodca správou míľnika projektu"

    milestone_id = fields.Many2one(
        "tenenet.project.milestone",
        string="Existujúci míľnik",
        readonly=True,
    )
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        readonly=True,
    )
    name = fields.Char(string="Míľnik", required=True)
    date = fields.Date(string="Dátum", required=True)
    note = fields.Text(string="Poznámka")

    attachment_ids = fields.Many2many(
        "ir.attachment",
        string="Prílohy",
    )
    alert_partner_ids = fields.Many2many(
        "res.partner",
        string="Príjemcovia upozornenia",
    )
    alert_lead_amount = fields.Integer(string="Upozorniť pred", default=1)
    alert_lead_unit = fields.Selection(
        [("day", "Dni"), ("week", "Týždne"), ("month", "Mesiace")],
        string="Jednotka",
        default="month",
        required=True,
    )

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        milestone_id = vals.get("milestone_id") or self.env.context.get("default_milestone_id")
        project_id = vals.get("project_id") or self.env.context.get("default_project_id")

        if milestone_id:
            milestone = self.env["tenenet.project.milestone"].sudo().browse(milestone_id)
            if milestone.attachment_ids:
                vals["attachment_ids"] = [(6, 0, milestone.attachment_ids.ids)]
            rule = milestone.alert_rule_id  # already sudo-browsed
            if rule:
                partner_ids = rule.recipient_partner_ids.ids
                if partner_ids:
                    vals["alert_partner_ids"] = [(6, 0, partner_ids)]
                date_cond = rule.condition_ids.filtered(lambda c: c.field_name == "date")[:1]
                if date_cond:
                    vals["alert_lead_amount"] = date_cond.relative_amount or 1
                    vals["alert_lead_unit"] = date_cond.relative_unit or "month"
            else:
                vals.update(self._default_alert_from_project(project_id))
        elif project_id:
            vals.update(self._default_alert_from_project(project_id))

        return vals

    def _default_alert_from_project(self, project_id):
        if not project_id:
            return {}
        project = self.env["tenenet.project"].browse(project_id)
        pm = project.project_manager_id
        partner = pm.user_id.partner_id if pm and pm.user_id else False
        if partner and partner.email:
            return {"alert_partner_ids": [(6, 0, [partner.id])]}
        return {}

    def action_confirm(self):
        self.ensure_one()
        self.project_id._check_milestone_manage_access()
        vals = {
            "project_id": self.project_id.id,
            "name": self.name,
            "date": self.date,
            "note": self.note,
        }
        if self.milestone_id:
            self.milestone_id.write(vals)
            milestone = self.milestone_id
        else:
            milestone = self.env["tenenet.project.milestone"].create(vals)

        # Sync attachments: reassociate any new uploads to the milestone record
        for attachment in self.attachment_ids:
            if attachment.res_model != "tenenet.project.milestone" or attachment.res_id != milestone.id:
                attachment.sudo().write({
                    "res_model": "tenenet.project.milestone",
                    "res_id": milestone.id,
                })
        milestone.sudo().write({"attachment_ids": [(6, 0, self.attachment_ids.ids)]})

        milestone._sync_alert_rule(
            partner_ids=self.alert_partner_ids.ids,
            lead_amount=self.alert_lead_amount or 1,
            lead_unit=self.alert_lead_unit or "month",
        )
        return {"type": "ir.actions.act_window_close"}

    def action_delete(self):
        self.ensure_one()
        self.project_id._check_milestone_manage_access()
        if self.milestone_id:
            self.milestone_id.unlink()
        return {"type": "ir.actions.act_window_close"}
