from odoo import fields, models


class TenenetProjectAssignmentRemoveWizard(models.TransientModel):
    _name = "tenenet.project.assignment.remove.wizard"
    _description = "Sprievodca odstránením priradenia zamestnanca"

    assignment_id = fields.Many2one(
        "tenenet.project.assignment",
        string="Priradenie",
        required=True,
        readonly=True,
    )
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        related="assignment_id.project_id",
        readonly=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        related="assignment_id.employee_id",
        readonly=True,
    )

    def action_archive_assignment(self):
        self.ensure_one()
        self.assignment_id.write({"active": False})
        return {"type": "ir.actions.act_window_close"}

    def action_delete_assignment(self):
        self.ensure_one()
        self.assignment_id.unlink()
        return {"type": "ir.actions.act_window_close"}
