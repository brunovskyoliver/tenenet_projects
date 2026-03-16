from odoo import api, fields, models


class TenenetProgram(models.Model):
    _name = "tenenet.program"
    _description = "Program TENENET"
    _order = "name"

    name = fields.Char(string="Názov programu", required=True)
    code = fields.Char(string="Kód programu", required=True)
    description = fields.Text(string="Popis")
    active = fields.Boolean(string="Aktívny", default=True)
    headcount = fields.Float(string="Počet ľudí (FTE)", digits=(10, 2))
    allocation_pct = fields.Float(
        string="Alokačné %",
        digits=(6, 4),
        compute="_compute_allocation_pct",
        store=True,
    )
    project_ids = fields.One2many("tenenet.project", "program_id", string="Projekty")

    _unique_code = models.Constraint("UNIQUE(code)", "Kód programu musí byť jedinečný.")

    @api.depends("headcount")
    def _compute_allocation_pct(self):
        all_programs = self.search([])
        total_headcount = sum(all_programs.mapped("headcount"))
        for program in self:
            program.allocation_pct = (program.headcount / total_headcount) if total_headcount else 0.0
