from odoo import api, fields, models


class TenenetProgram(models.Model):
    _name = "tenenet.program"
    _description = "Program TENENET"
    _order = "name"

    name = fields.Char(string="Názov programu", required=True)
    code = fields.Char(string="Kód programu", required=True)
    description = fields.Text(string="Popis")
    active = fields.Boolean(string="Aktívny", default=True)
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
