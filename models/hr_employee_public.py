from odoo import fields, models


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    service_ids = fields.One2many(
        "tenenet.employee.service",
        compute="_compute_service_ids",
        string="Služby",
        compute_sudo=True,
    )

    def _compute_service_ids(self):
        for employee in self:
            employee.service_ids = employee.employee_id.sudo().service_ids
