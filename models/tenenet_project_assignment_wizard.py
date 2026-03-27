from odoo import api, fields, models


class TenenetProjectAssignmentWizard(models.TransientModel):
    _name = "tenenet.project.assignment.wizard"
    _description = "Sprievodca pridaním priradenia zamestnanca k projektu"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        readonly=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
    )
    date_start = fields.Date(string="Začiatok priradenia")
    date_end = fields.Date(string="Koniec priradenia")
    allocation_ratio = fields.Float(
        string="Úväzok na projekte (%)",
        digits=(5, 2),
        default=100.0,
    )
    wage_hm = fields.Float(
        string="Hodinová mzda HM (brutto)",
        digits=(10, 4),
    )
    wage_ccp = fields.Float(
        string="Hodinová sadzba CCP (celková cena práce)",
        digits=(10, 4),
    )

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if self.employee_id:
            avg_hm, avg_ccp = self.env["tenenet.project.assignment"]._default_rates_for_employee(
                self.employee_id
            )
            self.wage_hm = avg_hm
            self.wage_ccp = avg_ccp

    def action_confirm(self):
        self.ensure_one()
        self.env["tenenet.project.assignment"].create({
            "project_id": self.project_id.id,
            "employee_id": self.employee_id.id,
            "date_start": self.date_start,
            "date_end": self.date_end,
            "allocation_ratio": self.allocation_ratio,
            "wage_hm": self.wage_hm,
            "wage_ccp": self.wage_ccp,
        })
        return {"type": "ir.actions.act_window_close"}
