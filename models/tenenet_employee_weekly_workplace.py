from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class TenenetEmployeeWeeklyWorkplace(models.Model):
    _name = "tenenet.employee.weekly.workplace"
    _description = "Týždenný rozvrh pracovísk zamestnanca"
    _order = "employee_id, weekday, time_from, id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
        index=True,
    )
    weekday = fields.Selection(
        [
            ("0", "Pondelok"),
            ("1", "Utorok"),
            ("2", "Streda"),
            ("3", "Štvrtok"),
            ("4", "Piatok"),
            ("5", "Sobota"),
            ("6", "Nedeľa"),
        ],
        string="Deň",
        required=True,
        default="0",
    )
    time_from = fields.Float(string="Od", required=True)
    time_to = fields.Float(string="Do", required=True)
    site_id = fields.Many2one(
        "tenenet.project.site",
        string="Pracovisko",
        required=True,
        ondelete="restrict",
        domain=[("site_type", "in", ["prevadzka", "centrum"])],
    )

    @api.model
    def _tenenet_is_hr_manager(self):
        return self.env.is_superuser() or self.env.user.has_group("hr.group_hr_manager")

    def _tenenet_check_owner_access(self):
        if self._tenenet_is_hr_manager():
            return
        current_user = self.env.user
        for rec in self:
            if rec.employee_id.user_id == current_user:
                continue
            if current_user in rec.employee_id.service_manager_user_ids:
                raise UserError(_("Nadriadený môže týždenný rozvrh pracovísk iba čítať."))
            raise UserError(_("Môžete upravovať iba vlastný týždenný rozvrh pracovísk."))

    @api.model
    def _tenenet_check_create_access(self, vals_list):
        if self._tenenet_is_hr_manager():
            return

        employee_ids = {vals.get("employee_id") for vals in vals_list if vals.get("employee_id")}
        if not employee_ids:
            return

        employees = {
            employee.id: employee
            for employee in self.env["hr.employee"].browse(employee_ids).exists()
        }
        current_user = self.env.user
        for vals in vals_list:
            employee_id = vals.get("employee_id")
            if not employee_id:
                continue
            employee = employees.get(employee_id)
            if not employee:
                continue
            if employee.user_id == current_user:
                continue
            if current_user in employee.service_manager_user_ids:
                raise UserError(_("Nadriadený môže týždenný rozvrh pracovísk iba čítať."))
            raise UserError(_("Môžete upravovať iba vlastný týždenný rozvrh pracovísk."))

    @api.model_create_multi
    def create(self, vals_list):
        self._tenenet_check_create_access(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        self._tenenet_check_owner_access()
        result = super().write(vals)
        self._tenenet_check_owner_access()
        return result

    def unlink(self):
        self._tenenet_check_owner_access()
        return super().unlink()

    @api.constrains("time_from", "time_to")
    def _check_time_range(self):
        for rec in self:
            if rec.time_from >= rec.time_to:
                raise ValidationError(_("Čas od musí byť menší ako čas do."))

    @api.constrains("employee_id", "site_id")
    def _check_site_allowed_for_employee(self):
        allowed_types = {"prevadzka", "centrum"}
        for rec in self:
            if rec.site_id.site_type not in allowed_types:
                raise ValidationError(_("Pracovisko v rozvrhu môže byť iba prevádzka alebo centrum."))
            allowed_sites = rec.employee_id.main_site_id | rec.employee_id.secondary_site_ids
            if rec.site_id not in allowed_sites:
                raise ValidationError(
                    _("Pracovisko v rozvrhu musí byť hlavné alebo vedľajšie pracovisko zamestnanca.")
                )

    @api.constrains("employee_id", "weekday", "time_from", "time_to")
    def _check_no_overlap(self):
        for rec in self:
            overlapping = self.search_count([
                ("id", "!=", rec.id),
                ("employee_id", "=", rec.employee_id.id),
                ("weekday", "=", rec.weekday),
                ("time_from", "<", rec.time_to),
                ("time_to", ">", rec.time_from),
            ])
            if overlapping:
                raise ValidationError(_("Rozvrh pracovísk sa v rovnaký deň nesmie prekrývať."))
