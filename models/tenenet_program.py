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
    allocation_pct_percentage = fields.Float(
        string="Alokačné percento",
        digits=(6, 4),
        compute="_compute_allocation_pct_percentage",
        store=True,
    )
    project_ids = fields.One2many("tenenet.project", "program_id", string="Projekty")
    pl_line_ids = fields.One2many("tenenet.pl.line", "program_id", string="P&L riadky")

    _unique_code = models.Constraint("UNIQUE(code)", "Kód programu musí byť jedinečný.")

    @api.depends("headcount")
    def _compute_allocation_pct(self):
        totals_data = self._read_group([], [], ["headcount:sum"])
        total_headcount = totals_data[0][0] if totals_data else 0.0
        for program in self:
            program.allocation_pct = (program.headcount / total_headcount) if total_headcount else 0.0
            
    @api.depends("headcount")
    def _compute_allocation_pct_percentage(self):
        totals_data = self._read_group([], [], ["headcount:sum"])
        total_headcount = totals_data[0][0] if totals_data else 0.0
        for program in self:
            program.allocation_pct_percentage = ((program.headcount / total_headcount) * 100) if total_headcount else 0.0

    @api.model
    def _recompute_allocation_pct_all(self):
        programs = self.search([])
        if programs:
            programs._compute_allocation_pct()
            programs._compute_allocation_pct_percentage()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._recompute_allocation_pct_all()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "headcount" in vals:
            self._recompute_allocation_pct_all()
        return result

    def unlink(self):
        linked_projects = self.env["tenenet.project"].with_context(active_test=False).search(
            [("program_id", "in", self.ids)]
        )
        if linked_projects:
            linked_projects.write({"program_id": False})
        result = super().unlink()
        self.env["tenenet.program"]._recompute_allocation_pct_all()
        return result
