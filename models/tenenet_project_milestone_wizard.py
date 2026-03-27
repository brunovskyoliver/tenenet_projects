from odoo import fields, models


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
        else:
            self.env["tenenet.project.milestone"].create(vals)
        return {"type": "ir.actions.act_window_close"}

    def action_delete(self):
        self.ensure_one()
        self.project_id._check_milestone_manage_access()
        if self.milestone_id:
            self.milestone_id.unlink()
        return {"type": "ir.actions.act_window_close"}
