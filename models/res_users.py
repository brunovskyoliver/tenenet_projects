from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date


class ResUsers(models.Model):
    _inherit = "res.users"

    _TENENET_HR_SUPER_ADMIN_XMLID = "tenenet_projects.group_tenenet_hr_super_admin"
    _TENENET_HR_ADMIN_XMLID = "tenenet_projects.group_tenenet_hr_admin"
    _TENENET_HR_PROJECT_ADMIN_XMLID = "tenenet_projects.group_tenenet_hr_project_admin"
    _TENENET_HELPDESK_USER_XMLID = "tenenet_projects.group_tenenet_helpdesk_user"
    _TENENET_HELPDESK_EDITOR_XMLID = "tenenet_projects.group_tenenet_helpdesk_editor"
    _TENENET_HELPDESK_MANAGER_XMLID = "tenenet_projects.group_tenenet_helpdesk_manager"

    bio = fields.Html(
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

    @api.model
    def _tenenet_get_hr_card_groups(self):
        return {
            "super_admin": self.env.ref(self._TENENET_HR_SUPER_ADMIN_XMLID, raise_if_not_found=False),
            "admin": self.env.ref(self._TENENET_HR_ADMIN_XMLID, raise_if_not_found=False),
            "project_admin": self.env.ref(self._TENENET_HR_PROJECT_ADMIN_XMLID, raise_if_not_found=False),
        }

    @api.model
    def _tenenet_get_helpdesk_groups(self):
        return {
            "user": self.env.ref(self._TENENET_HELPDESK_USER_XMLID, raise_if_not_found=False),
            "editor": self.env.ref(self._TENENET_HELPDESK_EDITOR_XMLID, raise_if_not_found=False),
            "manager": self.env.ref(self._TENENET_HELPDESK_MANAGER_XMLID, raise_if_not_found=False),
            "helpdesk_user": self.env.ref("helpdesk.group_helpdesk_user", raise_if_not_found=False),
            "helpdesk_manager": self.env.ref("helpdesk.group_helpdesk_manager", raise_if_not_found=False),
        }

    @api.model
    def _tenenet_get_hr_card_admin_application_groups(self):
        return [
            self.env.ref("hr.group_hr_manager", raise_if_not_found=False),
            self.env.ref("hr_holidays.group_hr_holidays_manager", raise_if_not_found=False),
            self.env.ref("hr_expense.group_hr_expense_manager", raise_if_not_found=False),
        ]

    @api.model
    def _tenenet_has_explicit_hr_card_admin_role_from_group_ids(self, group_ids):
        groups = self._tenenet_get_hr_card_groups()
        group_ids = set(group_ids or [])
        system_group = self.env.ref("base.group_system", raise_if_not_found=False)
        return bool(
            (groups["super_admin"] and groups["super_admin"].id in group_ids)
            or (groups["admin"] and groups["admin"].id in group_ids)
            or (system_group and system_group.id in group_ids)
        )

    @api.model
    def _tenenet_get_hr_card_role_level_from_group_ids(self, group_ids):
        groups = self._tenenet_get_hr_card_groups()
        group_ids = set(group_ids or [])
        system_group = self.env.ref("base.group_system", raise_if_not_found=False)
        hr_manager_group = self.env.ref("hr.group_hr_manager", raise_if_not_found=False)
        if (groups["super_admin"] and groups["super_admin"].id in group_ids) or (
            system_group and system_group.id in group_ids
        ):
            return 3
        if (groups["admin"] and groups["admin"].id in group_ids) or (
            hr_manager_group and hr_manager_group.id in group_ids
        ):
            return 2
        if groups["project_admin"] and groups["project_admin"].id in group_ids:
            return 1
        return 0

    def _tenenet_get_hr_card_role_level(self):
        self.ensure_one()
        return self._tenenet_get_hr_card_role_level_from_group_ids(self.group_ids.ids)

    def _tenenet_get_hr_card_role_code(self):
        self.ensure_one()
        level = self._tenenet_get_hr_card_role_level()
        if level >= 3:
            return "super_admin"
        if level >= 2:
            return "admin"
        if level >= 1:
            return "project_admin"
        return False

    def _tenenet_get_hr_card_role_label(self):
        self.ensure_one()
        labels = {
            "super_admin": "Super admin",
            "admin": "Admin",
            "project_admin": "Admin projektovy",
        }
        return labels.get(self._tenenet_get_hr_card_role_code()) or "Bez role"

    @api.model
    def _tenenet_apply_group_commands(self, initial_group_ids, commands):
        result = set(initial_group_ids or [])
        for command in commands or []:
            if not isinstance(command, (list, tuple)) or not command:
                continue
            operation = command[0]
            if operation == 6:
                result = set(command[2] or [])
            elif operation == 5:
                result.clear()
            elif operation == 4:
                result.add(command[1])
            elif operation == 3:
                result.discard(command[1])
        return result

    def _tenenet_sync_hr_project_admin_group_membership(self):
        groups = self._tenenet_get_hr_card_groups()
        project_admin_group = groups["project_admin"]
        admin_group = groups["admin"]
        super_admin_group = groups["super_admin"]
        if not project_admin_group:
            return

        Project = self.env["tenenet.project"].sudo()
        for user in self.filtered(lambda rec: rec.share is False):
            current_group_ids = set(user.group_ids.ids)
            has_higher_role = bool(
                (super_admin_group and super_admin_group.id in current_group_ids)
                or (admin_group and admin_group.id in current_group_ids)
                or user.has_group("base.group_system")
                or user.has_group("hr.group_hr_manager")
            )
            should_have_project_admin = bool(Project.search_count([
                ("active", "=", True),
                ("project_manager_id.user_id", "=", user.id),
            ]))
            if has_higher_role:
                if project_admin_group.id in current_group_ids:
                    user.sudo().write({"group_ids": [(3, project_admin_group.id)]})
                continue
            if should_have_project_admin and project_admin_group.id not in current_group_ids:
                user.sudo().write({"group_ids": [(4, project_admin_group.id)]})
            elif not should_have_project_admin and project_admin_group.id in current_group_ids:
                user.sudo().write({"group_ids": [(3, project_admin_group.id)]})

    def _tenenet_sync_hr_card_admin_application_groups(self):
        if self.env.context.get("tenenet_skip_hr_card_admin_group_sync"):
            return

        managed_groups = [group for group in self._tenenet_get_hr_card_admin_application_groups() if group]
        if not managed_groups:
            return

        for user in self.filtered(lambda rec: rec.share is False):
            current_group_ids = set(user.group_ids.ids)
            should_have_admin_groups = self._tenenet_has_explicit_hr_card_admin_role_from_group_ids(current_group_ids)
            commands = []
            for group in managed_groups:
                if should_have_admin_groups and group.id not in current_group_ids:
                    commands.append((4, group.id))
                elif not should_have_admin_groups and group.id in current_group_ids:
                    commands.append((3, group.id))
            if commands:
                user.with_context(tenenet_skip_hr_card_admin_group_sync=True).sudo().write({
                    "group_ids": commands,
                })

    def _tenenet_sync_helpdesk_application_groups(self):
        if self.env.context.get("tenenet_skip_helpdesk_group_sync"):
            return

        groups = self._tenenet_get_helpdesk_groups()
        tenenet_groups = [groups["user"], groups["editor"], groups["manager"]]
        helpdesk_user_group = groups["helpdesk_user"]
        helpdesk_manager_group = groups["helpdesk_manager"]
        if not helpdesk_user_group or not helpdesk_manager_group:
            return

        for user in self.filtered(lambda rec: rec.share is False):
            current_group_ids = set(user.group_ids.ids)
            has_tenenet_helpdesk = any(group and group.id in current_group_ids for group in tenenet_groups)
            has_tenenet_helpdesk_manager = bool(groups["manager"] and groups["manager"].id in current_group_ids)
            commands = []
            if has_tenenet_helpdesk_manager:
                if helpdesk_manager_group.id not in current_group_ids:
                    commands.append((4, helpdesk_manager_group.id))
            elif helpdesk_manager_group.id in current_group_ids:
                commands.append((3, helpdesk_manager_group.id))

            if has_tenenet_helpdesk and not has_tenenet_helpdesk_manager:
                if helpdesk_user_group.id not in current_group_ids:
                    commands.append((4, helpdesk_user_group.id))
            elif not has_tenenet_helpdesk and helpdesk_user_group.id in current_group_ids:
                commands.append((3, helpdesk_user_group.id))

            if commands:
                user.with_context(tenenet_skip_helpdesk_group_sync=True).sudo().write({
                    "group_ids": commands,
                })

    def _tenenet_check_hr_card_role_write_hierarchy(self, vals):
        if self.env.is_superuser() or "group_ids" not in vals:
            return

        current_user = self.env.user
        current_user_level = current_user._tenenet_get_hr_card_role_level()
        if current_user.has_group("base.group_system"):
            current_user_level = 3

        for user in self:
            target_level = user._tenenet_get_hr_card_role_level()
            if current_user_level < 3 and target_level > current_user_level:
                raise UserError("Nemôžete meniť HR rolu používateľa s vyššou úrovňou.")

            next_group_ids = self._tenenet_apply_group_commands(user.group_ids.ids, vals.get("group_ids"))
            next_level = self._tenenet_get_hr_card_role_level_from_group_ids(next_group_ids)
            if target_level >= 2 and next_level < target_level and current_user_level < 3:
                raise UserError("Používateľa s rolou Super admin alebo Admin nemôžete znížiť na nižšiu HR rolu.")

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._tenenet_sync_hr_project_admin_group_membership()
        users._tenenet_sync_hr_card_admin_application_groups()
        users._tenenet_sync_helpdesk_application_groups()
        return users

    def write(self, vals):
        self._tenenet_check_hr_card_role_write_hierarchy(vals)
        if (
            not self.env.is_superuser()
            and set(self.ids) == {self.env.user.id}
            and set(vals).issubset(set(self.SELF_WRITEABLE_FIELDS))
        ):
            return super(ResUsers, self.sudo()).write(vals)
        result = super().write(vals)
        if "group_ids" in vals:
            self._tenenet_sync_hr_project_admin_group_membership()
            self._tenenet_sync_hr_card_admin_application_groups()
            self._tenenet_sync_helpdesk_application_groups()
        return result

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
