from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    tenenet_number = fields.Integer(string="Interné číslo")
    title_academic = fields.Char(string="Titul")
    position = fields.Char(string="Pozícia", related="job_id.name", store=True, readonly=True, translate=False)
    education_info = fields.Text(string="Vzdelanie")
    work_hours = fields.Float(
        string="Pracovné hodiny (mesiac)",
        digits=(10, 2),
        compute="_compute_workload_from_calendar",
        store=True,
        help="Mesačný baseline z kalendára: 160h pri 100% úväzku.",
    )
    work_ratio = fields.Float(
        string="Úväzok (%)",
        digits=(5, 2),
        compute="_compute_workload_from_calendar",
        store=True,
        help="Vypočítané z resource_calendar_id.hours_per_day voči 8h plnému úväzku.",
    )
    hourly_rate = fields.Float(string="Hodinová sadzba", digits=(10, 2))
    allocation_ids = fields.One2many(
        "tenenet.employee.allocation",
        "employee_id",
        string="Alokácie",
    )
    utilization_ids = fields.One2many(
        "tenenet.utilization",
        "employee_id",
        string="Vyťaženosť",
    )
    pl_line_ids = fields.One2many(
        "tenenet.pl.line",
        "employee_id",
        string="P&L riadky",
    )
    assignment_ids = fields.One2many(
        "tenenet.project.assignment",
        "employee_id",
        string="Priradenia k projektom",
    )
    tenenet_cost_ids = fields.One2many(
        "tenenet.employee.tenenet.cost",
        "employee_id",
        string="Tenenet náklady",
    )

    @api.depends("resource_calendar_id", "resource_calendar_id.hours_per_day")
    def _compute_workload_from_calendar(self):
        for rec in self:
            hours_per_day = rec.resource_calendar_id.hours_per_day or 8.0
            ratio = (hours_per_day / 8.0) * 100.0 if hours_per_day > 0 else 0.0
            rec.work_ratio = ratio
            rec.work_hours = 160.0 * ratio / 100.0
