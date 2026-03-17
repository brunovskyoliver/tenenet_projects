from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    tenenet_number = fields.Integer(string="Interné číslo")
    title_academic = fields.Char(string="Titul")
    position = fields.Char(string="Pozícia", related="job_id.name", store=True, readonly=True)
    education_info = fields.Text(string="Vzdelanie")
    work_hours = fields.Float(string="Úväzok (hod/deň)", digits=(4, 1))
    work_ratio = fields.Float(string="Úväzok (%)", digits=(5, 2))
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
