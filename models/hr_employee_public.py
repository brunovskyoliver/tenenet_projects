from odoo import fields, models


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    main_site_id = fields.Many2one("tenenet.project.site", readonly=True)
    bio = fields.Text(readonly=True)
    all_site_names = fields.Char(readonly=True)
    all_job_names = fields.Char(readonly=True)
    secondary_site_ids = fields.Many2many(
        "tenenet.project.site",
        compute="_compute_profile_links",
        string="Vedľajšie miesta práce",
        compute_sudo=True,
    )
    additional_job_ids = fields.Many2many(
        "hr.job",
        compute="_compute_profile_links",
        string="Vedľajšie pozície",
        compute_sudo=True,
    )
    evaluation_ids = fields.One2many(
        "tenenet.employee.evaluation",
        compute="_compute_evaluation_ids",
        string="Hodnotenia",
    )

    service_ids = fields.One2many(
        "tenenet.employee.service",
        compute="_compute_service_ids",
        string="Služby",
        compute_sudo=True,
    )

    def _compute_profile_links(self):
        for employee in self:
            employee.secondary_site_ids = employee.employee_id.sudo().secondary_site_ids
            employee.additional_job_ids = employee.employee_id.sudo().additional_job_ids

    def _compute_service_ids(self):
        for employee in self:
            employee.service_ids = employee.employee_id.sudo().service_ids

    def _compute_evaluation_ids(self):
        Evaluation = self.env["tenenet.employee.evaluation"]
        for employee in self:
            employee.evaluation_ids = Evaluation.search(
                [("employee_id", "=", employee.employee_id.id)],
                order="year desc, id desc",
            )
