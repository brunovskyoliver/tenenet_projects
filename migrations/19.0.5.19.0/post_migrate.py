from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    group = env.ref("tenenet_projects.group_tenenet_garant_pm", raise_if_not_found=False)
    if not group:
        return

    active_projects = env["tenenet.project"].sudo().search([("active", "=", True)])
    assigned_employees = active_projects.mapped("odborny_garant_id") | active_projects.mapped("project_manager_id")
    hidden_users = env["res.users"].sudo().search([("group_ids", "in", group.id)])
    hidden_employees = hidden_users.mapped("employee_ids")

    env["tenenet.project"].sudo()._sync_garant_pm_group(assigned_employees | hidden_employees)
    users_without_employee = hidden_users.filtered(lambda user: not user.employee_ids)
    if users_without_employee:
        users_without_employee.write({"group_ids": [(3, group.id)]})
