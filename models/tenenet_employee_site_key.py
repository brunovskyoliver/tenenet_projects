from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TenenetEmployeeSiteKey(models.Model):
    _name = "tenenet.employee.site.key"
    _description = "Kľúč zamestnanca k prevádzke alebo centru"
    _order = "site_id, employee_id, id"

    _unique_employee_site = models.Constraint(
        "UNIQUE(employee_id, site_id)",
        "Zamestnanec už má priradený kľúč k tejto prevádzke alebo centru.",
    )

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
    )
    site_id = fields.Many2one(
        "tenenet.project.site",
        string="Prevádzka / centrum",
        required=True,
        ondelete="cascade",
        domain="[('site_type', 'in', ['prevadzka', 'centrum'])]",
    )
    work_phone = fields.Char(
        string="Telefón",
        related="employee_id.work_phone",
        readonly=True,
    )
    active = fields.Boolean(string="Aktívne", default=True)

    @api.constrains("site_id")
    def _check_site_type(self):
        for rec in self:
            if rec.site_id and rec.site_id.site_type not in {"prevadzka", "centrum"}:
                raise ValidationError("Kľúč možno priradiť len k prevádzke alebo centru.")
