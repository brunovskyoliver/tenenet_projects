from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.tools import format_date


class ResUsers(models.Model):
    _inherit = "res.users"

    bio = fields.Text(
        related="employee_id.bio",
        string="Bio",
        readonly=False,
        related_sudo=True,
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["bio"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["bio"]

    def write(self, vals):
        if (
            not self.env.is_superuser()
            and set(self.ids) == {self.env.user.id}
            and set(vals).issubset(set(self.SELF_WRITEABLE_FIELDS))
        ):
            return super(ResUsers, self.sudo()).write(vals)
        return super().write(vals)

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if "lang" in fields_list and "lang" not in defaults:
            defaults["lang"] = "sk_SK"
        return defaults

    @api.model
    def get_home_menu_previous_month_utilization(self):
        user = self.env.user
        employee = user.employee_id or user.employee_ids[:1]
        if not employee:
            return False

        current_month_start = fields.Date.context_today(self).replace(day=1)
        previous_period = (current_month_start + relativedelta(months=-1)).replace(day=1)
        utilization = self.env["tenenet.utilization"].sudo().search(
            [
                ("employee_id", "=", employee.id),
                ("period", "=", previous_period),
            ],
            limit=1,
        )
        if not utilization:
            return False

        utilization_percentage = utilization.utilization_percentage or 0.0
        return {
            "employee_name": employee.name or "",
            "period": fields.Date.to_string(previous_period),
            "period_label": format_date(self.env, previous_period, date_format="MMMM yyyy"),
            "utilization_percentage": utilization_percentage,
            "utilization_percentage_display": f"{utilization_percentage:.1f} %",
            "utilization_status": utilization.utilization_status or "warning",
            "progress_width": max(0.0, min(utilization_percentage, 100.0)),
        }
