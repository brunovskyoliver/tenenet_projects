from odoo import api, fields, models


class TenenetProgram(models.Model):
    _name = "tenenet.program"
    _description = "Program TENENET"
    _order = "name"

    name = fields.Char(string="Názov programu", required=True)
    code = fields.Char(string="Kód programu", required=True)
    description = fields.Text(string="Popis")
    active = fields.Boolean(string="Aktívny", default=True)
    program_kind = fields.Selection(
        [
            ("service", "Služba"),
            ("management", "Manažment"),
            ("support", "Podpora"),
        ],
        string="Typ programu",
        default="service",
        required=True,
    )
    headcount = fields.Float(
        string="Počet ľudí (FTE)",
        digits=(10, 2),
        compute="_compute_headcount",
        store=True,
        readonly=True,
        help="Počet aktívnych priradení zamestnancov na aktívnych projektoch patriacich do programu.",
    )
    allocation_pct = fields.Float(
        string="Alokačné %",
        digits=(6, 4),
        compute="_compute_allocation_pct",
    )
    allocation_pct_percentage = fields.Float(
        string="Alokačné percento",
        digits=(6, 4),
        compute="_compute_allocation_pct_percentage",
    )
    reporting_fte = fields.Float(
        string="Reporting FTE",
        digits=(10, 4),
        compute="_compute_reporting_fte",
        store=True,
        readonly=True,
    )
    operating_allocation_pct = fields.Float(
        string="Prevádzková alokácia %",
        digits=(6, 4),
        compute="_compute_operating_allocation_pct",
        readonly=True,
    )
    project_ids = fields.Many2many(
        "tenenet.project",
        "tenenet_project_program_rel",
        "program_id",
        "project_id",
        string="Projekty",
    )
    pl_line_ids = fields.One2many("tenenet.pl.line", "program_id", string="P&L riadky")

    _unique_code = models.Constraint("UNIQUE(code)", "Kód programu musí byť jedinečný.")

    @api.depends(
        "project_ids",
        "project_ids.active",
        "project_ids.assignment_ids",
        "project_ids.assignment_ids.active",
    )
    def _compute_headcount(self):
        assignment_model = self.env["tenenet.project.assignment"].with_context(active_test=False)
        for program in self:
            program.headcount = float(assignment_model.search_count([
                ("active", "=", True),
                ("project_id.active", "=", True),
                ("project_id.program_ids", "in", program.id),
            ]))

    @api.depends("headcount")
    def _compute_allocation_pct(self):
        total_headcount = sum(self.search([]).mapped("headcount"))
        for program in self:
            program.allocation_pct = (program.headcount / total_headcount) if total_headcount else 0.0

    @api.depends("headcount")
    def _compute_allocation_pct_percentage(self):
        total_headcount = sum(self.search([]).mapped("headcount"))
        for program in self:
            program.allocation_pct_percentage = ((program.headcount / total_headcount) * 100) if total_headcount else 0.0

    @api.depends(
        "project_ids.reporting_program_id",
        "project_ids.assignment_ids.active",
        "project_ids.assignment_ids.allocation_ratio",
    )
    def _compute_reporting_fte(self):
        assignment_model = self.env["tenenet.project.assignment"].with_context(active_test=False)
        for program in self:
            assignments = assignment_model.search([
                ("active", "=", True),
                ("project_id.reporting_program_id", "=", program.id),
                ("project_id.active", "=", True),
            ])
            program.reporting_fte = sum(assignments.mapped("allocation_ratio")) / 100.0

    @api.depends("reporting_fte")
    def _compute_operating_allocation_pct(self):
        total_fte = sum(self.search([]).mapped("reporting_fte"))
        for program in self:
            program.operating_allocation_pct = (
                (program.reporting_fte / total_fte) if total_fte else 0.0
            )
