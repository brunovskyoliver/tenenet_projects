from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrEmployeePublic(models.Model):
    _inherit = "hr.employee.public"

    main_site_id = fields.Many2one(
        "tenenet.project.site",
        related="employee_id.main_site_id",
        readonly=True,
    )
    main_site_address_display = fields.Char(
        related="employee_id.main_site_address_display",
        readonly=True,
    )
    bio = fields.Text(related="employee_id.bio", readonly=True)
    all_site_names = fields.Char(related="employee_id.all_site_names", readonly=True)
    all_job_names = fields.Char(related="employee_id.all_job_names", readonly=True)
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
    weekly_workplace_ids = fields.One2many(
        "tenenet.employee.weekly.workplace",
        compute="_compute_weekly_workplace_ids",
        string="Týždenný rozvrh pracovísk",
        compute_sudo=True,
    )
    tenenet_is_card_owner = fields.Boolean(
        compute="_compute_tenenet_access_flags",
        string="Vlastná karta",
    )
    tenenet_can_request_employee_update = fields.Boolean(
        compute="_compute_tenenet_access_flags",
        string="Môže požiadať o aktualizáciu",
    )
    tenenet_can_open_private_employee_card = fields.Boolean(
        compute="_compute_tenenet_access_flags",
        string="Môže otvoriť celú kartu",
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

    def _compute_weekly_workplace_ids(self):
        for employee in self:
            employee.weekly_workplace_ids = employee.employee_id.sudo().weekly_workplace_ids

    @api.depends_context("uid")
    def _compute_tenenet_access_flags(self):
        current_user = self.env.user
        for employee in self:
            private_employee = employee.employee_id.sudo()
            is_owner = bool(private_employee.user_id == current_user)
            employee.tenenet_is_card_owner = is_owner
            employee.tenenet_can_request_employee_update = bool(
                current_user.has_group("hr.group_hr_manager") or is_owner
            )
            employee.tenenet_can_open_private_employee_card = employee._tenenet_can_user_open_private_card(
                current_user
            )

    def _tenenet_can_user_open_private_card(self, user):
        self.ensure_one()
        private_employee = self.employee_id.sudo()
        return bool(
            user.has_group("hr.group_hr_manager")
            or private_employee.user_id == user
            or private_employee.service_manager_user_ids.filtered(lambda manager: manager == user)
            or private_employee._tenenet_is_project_manager_employee_user(user)
        )

    def _tenenet_private_employee_form_action(self):
        self.ensure_one()
        private_employee = self.employee_id.sudo()
        private_form = self.env.ref("hr.view_employee_form", raise_if_not_found=False)
        action = {
            "type": "ir.actions.act_window",
            "name": _("Karta zamestnanca"),
            "res_model": "hr.employee",
            "res_id": private_employee.id,
            "view_mode": "form",
            "views": (
                [(private_form.id, "form")]
                if private_form
                else [(False, "form")]
            ),
            "target": "current",
            "context": {
                "active_id": private_employee.id,
                "active_ids": [private_employee.id],
                "active_model": "hr.employee",
                "tenenet_private_card_access_employee_ids": [private_employee.id],
                "chat_icon": True,
                "form_view_initial_mode": "readonly",
            },
        }
        if private_form:
            action["view_id"] = private_form.id
        return action

    def action_tenenet_open_private_employee_card(self):
        self.ensure_one()
        current_user = self.env.user
        if not self._tenenet_can_user_open_private_card(current_user):
            raise UserError(_("Nemáte oprávnenie otvoriť celú kartu tohto zamestnanca."))
        return self._tenenet_private_employee_form_action()

    def action_tenenet_open_employee_card(self):
        self.ensure_one()
        return self.get_formview_action()

    def get_formview_action(self, access_uid=None):
        self.ensure_one()
        user = self.env.user
        if access_uid:
            user = self.env["res.users"].browse(access_uid).sudo()
        if self._tenenet_can_user_open_private_card(user):
            return self._tenenet_private_employee_form_action()
        return super().get_formview_action(access_uid=access_uid)
