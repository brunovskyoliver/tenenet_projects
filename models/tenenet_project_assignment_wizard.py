from datetime import date

from odoo import api, fields, models

from .tenenet_project_assignment import _ranges_overlap


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
    date_start = fields.Date(
        string="Začiatok priradenia",
        default=lambda self: self._default_date_start(),
    )
    date_end = fields.Date(
        string="Koniec priradenia",
        default=lambda self: self._default_date_end(),
    )
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
    free_ratio_for_period = fields.Float(
        string="Voľný úväzok v období (%)",
        digits=(5, 2),
        compute="_compute_free_ratio_for_period",
    )

    @api.model
    def _default_date_start(self):
        today = fields.Date.context_today(self)
        return date(today.year, 1, 1)

    @api.model
    def _default_date_end(self):
        today = fields.Date.context_today(self)
        return date(today.year, 12, 31)

    @api.depends("project_id", "project_id.program_ids", "project_id.ui_program_ids")
    def _compute_available_program_ids(self):
        for rec in self:
            rec.available_program_ids = rec.project_id.ui_program_ids or rec.project_id.program_ids

    @api.depends("employee_id", "date_start", "date_end")
    def _compute_free_ratio_for_period(self):
        Assignment = self.env["tenenet.project.assignment"].with_context(active_test=False)
        for rec in self:
            if not rec.employee_id:
                rec.free_ratio_for_period = 0.0
                continue

            start, end = rec._get_effective_date_range()
            overlapping_assignments = Assignment.search([
                ("employee_id", "=", rec.employee_id.id),
                ("active", "=", True),
            ])
            max_overlapping_ratio = sum(
                assignment.allocation_ratio
                for assignment in overlapping_assignments
                if _ranges_overlap(start, end, *assignment._get_effective_date_range())
            )
            rec.free_ratio_for_period = max(0.0, (rec.employee_id.work_ratio or 0.0) - max_overlapping_ratio)

    def _get_program_domain(self):
        self.ensure_one()
        return [("id", "in", self.available_program_ids.ids)]

    def _get_effective_date_range(self):
        self.ensure_one()
        start = self.date_start or self.project_id.date_start
        end = self.date_end or self.project_id.date_end

        if not start and not end:
            start = self._default_date_start()
            end = self._default_date_end()
        elif start and not end:
            end = date(start.year, 12, 31)
        elif end and not start:
            start = date(end.year, 1, 1)

        if start and end and start > end:
            start, end = end, start
        return start, end

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
                self.project_id._get_effective_reporting_program().filtered(lambda rec: rec in available_programs)
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
