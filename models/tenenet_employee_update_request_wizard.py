from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class TenenetEmployeeUpdateRequestWizard(models.TransientModel):
    _name = "tenenet.employee.update.request.wizard"
    _description = "Požiadavka na aktualizáciu karty zamestnanca"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        readonly=True,
    )
    request_text = fields.Text(string="Požiadavka", required=True)

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        employee = self.env["hr.employee"].browse(
            self.env.context.get("default_employee_id") or self.env.context.get("active_id")
        )
        if employee:
            defaults["employee_id"] = employee.id
        return defaults

    @api.model
    def _get_employee_update_helpdesk_team(self, employee=False):
        configured_id = self.env["ir.config_parameter"].sudo().get_param(
            "tenenet_projects.employee_update_helpdesk_team_id"
        )
        if configured_id:
            team = self.env["helpdesk.team"].sudo().browse(int(configured_id)).exists()
            if team:
                return team
        company = employee.company_id if employee else False
        return self.env["helpdesk.ticket"]._get_tenenet_internal_team(company=company)

    def _check_can_request_update(self):
        if self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager"):
            return
        for wizard in self:
            if wizard.employee_id.user_id != self.env.user:
                raise AccessError(_("Môžete požiadať iba o aktualizáciu vlastnej karty zamestnanca."))

    def action_confirm(self):
        self.ensure_one()
        self._check_can_request_update()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Aktualizovať"),
                "message": _("Požiadavky na aktualizáciu karty sú dočasne vypnuté."),
                "type": "warning",
                "sticky": False,
            },
        }
