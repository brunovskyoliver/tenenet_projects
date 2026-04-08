from odoo import api, fields, models


class TenenetProgram(models.Model):
    _name = "tenenet.program"
    _description = "Program TENENET"
    _order = "name"

    name = fields.Char(string="Názov programu", required=True)
    code = fields.Char(string="Kód programu", required=True)
    description = fields.Text(string="Popis")
    active = fields.Boolean(string="Aktívny", default=True)
    is_tenenet_internal = fields.Boolean(
        string="Interný TENENET program",
        default=False,
        help="Technický interný program, ktorý sa nemá zobrazovať v bežnom UI zoznamoch.",
    )
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
        readonly=True,
        help="Aktuálny FTE súčet aktívnych priradení zamestnancov v programe.",
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

    def _get_program_assignment_totals(self):
        assignments = self.env["tenenet.project.assignment"].with_context(active_test=False).search([
            ("active", "=", True),
            ("project_id.active", "=", True),
            ("program_id", "in", self.ids),
        ])
        totals = {
            program.id: {
                "fte": 0.0,
                "employees": set(),
            }
            for program in self
        }
        for assignment in assignments:
            ratio = assignment.effective_work_ratio or assignment.allocation_ratio or 0.0
            bucket = totals.setdefault(
                assignment.program_id.id,
                {"fte": 0.0, "employees": set()},
            )
            bucket["fte"] += ratio / 100.0
            if assignment.employee_id:
                bucket["employees"].add(assignment.employee_id.id)
        return totals

    @api.depends(
        "project_ids.assignment_ids.active",
        "project_ids.assignment_ids.program_id",
        "project_ids.assignment_ids.allocation_ratio",
        "project_ids.assignment_ids.effective_work_ratio",
        "project_ids.assignment_ids.employee_id",
        "project_ids.active",
    )
    def _compute_headcount(self):
        totals = self._get_program_assignment_totals()
        for program in self:
            if program.code == "ADMIN_TENENET":
                program.headcount = 0.0
                continue
            program.headcount = totals.get(program.id, {}).get("fte", 0.0)

    @api.depends("headcount")
    def _compute_allocation_pct(self):
        active_programs = self.search([("active", "=", True)]).filtered(
            lambda program: program.code != "ADMIN_TENENET"
        )
        total_headcount = sum(active_programs.mapped("headcount"))
        for program in self:
            if program.code == "ADMIN_TENENET":
                program.allocation_pct = False
                continue
            program.allocation_pct = (program.headcount / total_headcount) if total_headcount else 0.0

    @api.depends("headcount")
    def _compute_allocation_pct_percentage(self):
        active_programs = self.search([("active", "=", True)]).filtered(
            lambda program: program.code != "ADMIN_TENENET"
        )
        total_headcount = sum(active_programs.mapped("headcount"))
        for program in self:
            if program.code == "ADMIN_TENENET":
                program.allocation_pct_percentage = False
                continue
            program.allocation_pct_percentage = ((program.headcount / total_headcount) * 100) if total_headcount else 0.0

    @api.depends(
        "project_ids.assignment_ids.active",
        "project_ids.assignment_ids.program_id",
        "project_ids.assignment_ids.allocation_ratio",
        "project_ids.assignment_ids.effective_work_ratio",
        "project_ids.active",
    )
    def _compute_reporting_fte(self):
        totals = self._get_program_assignment_totals()
        for program in self:
            if program.code == "ADMIN_TENENET":
                program.reporting_fte = 0.0
                continue
            program.reporting_fte = totals.get(program.id, {}).get("fte", 0.0)

    @api.depends("reporting_fte")
    def _compute_operating_allocation_pct(self):
        active_programs = self.search([("active", "=", True)]).filtered(
            lambda program: program.code != "ADMIN_TENENET"
        )
        total_fte = sum(active_programs.mapped("reporting_fte"))
        for program in self:
            if program.code == "ADMIN_TENENET":
                program.operating_allocation_pct = False
                continue
            program.operating_allocation_pct = (
                (program.reporting_fte / total_fte) if total_fte else 0.0
            )
