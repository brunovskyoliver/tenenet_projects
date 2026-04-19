from odoo import api, models, _
from odoo.exceptions import UserError


class HrEmployeeSkill(models.Model):
    _inherit = "hr.employee.skill"

    def _tenenet_check_skill_write_access(self):
        if self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager"):
            return
        raise UserError(_("Znalosti zamestnanca môže upravovať iba HR administrátor."))

    @api.model_create_multi
    def create(self, vals_list):
        if not (self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager")):
            raise UserError(_("Znalosti zamestnanca môže upravovať iba HR administrátor."))
        return super().create(vals_list)

    def write(self, vals):
        self._tenenet_check_skill_write_access()
        return super().write(vals)

    def unlink(self):
        self._tenenet_check_skill_write_access()
        return super().unlink()
