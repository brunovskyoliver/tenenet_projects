from odoo import _, api, fields, models


class TenenetProjectMilestone(models.Model):
    _name = "tenenet.project.milestone"
    _description = "Míľnik projektu"
    _order = "date asc, sequence asc, id asc"

    sequence = fields.Integer(default=10)
    name = fields.Char(string="Míľnik", required=True)
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
    )
    date = fields.Date(string="Dátum", required=True)
    note = fields.Text(string="Poznámka")

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
        return super().write(vals)

    def unlink(self):
        self.mapped("project_id")._check_milestone_manage_access()
        return super().unlink()

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
