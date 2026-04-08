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
    program_id = fields.Many2one(
        "tenenet.program",
        string="Program",
        required=True,
    )
    available_program_ids = fields.Many2many(
        "tenenet.program",
        compute="_compute_available_program_ids",
    )
    date_start = fields.Date(string="Začiatok priradenia")
    date_end = fields.Date(string="Koniec priradenia")
    allocation_ratio = fields.Float(
        string="Úväzok na projekte (%)",
        digits=(5, 2),
        default=100.0,
    )
    settlement_only = fields.Boolean(
        string="Iba na zúčtovanie",
        default=False,
        help="Priradenie slúži iba na zúčtovanie alebo financovanie z iných zdrojov.",
    )
    wage_hm = fields.Float(
        string="Hodinová mzda HM (brutto)",
        digits=(10, 4),
    )

    @api.depends("project_id", "project_id.program_ids", "project_id.ui_program_ids")
    def _compute_available_program_ids(self):
        for rec in self:
            rec.available_program_ids = rec.project_id.ui_program_ids or rec.project_id.program_ids

    def _get_program_domain(self):
        self.ensure_one()
        return [("id", "in", self.available_program_ids.ids)]

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if self.employee_id:
            avg_hm, _avg_ccp = self.env["tenenet.project.assignment"]._default_rates_for_employee(
                self.employee_id
            )
            self.wage_hm = avg_hm

    @api.onchange("project_id")
    def _onchange_project_id(self):
        domain = {"program_id": []}
        if self.project_id:
            domain["program_id"] = self._get_program_domain()
            available_programs = self.available_program_ids
            self.program_id = (
                self.project_id.reporting_program_id.filtered(lambda rec: rec in available_programs)
                or available_programs.filtered(lambda rec: rec.code != "ADMIN_TENENET")[:1]
                or available_programs[:1]
                or self.project_id.program_ids[:1]
            )
        else:
            self.program_id = False
        return {"domain": domain}

    def action_confirm(self):
        self.ensure_one()
        self.env["tenenet.project.assignment"].create({
            "project_id": self.project_id.id,
            "employee_id": self.employee_id.id,
            "program_id": self.program_id.id,
            "date_start": self.date_start,
            "date_end": self.date_end,
            "allocation_ratio": self.allocation_ratio,
            "settlement_only": self.settlement_only,
            "wage_hm": self.wage_hm,
        })
        return {"type": "ir.actions.act_window_close"}
