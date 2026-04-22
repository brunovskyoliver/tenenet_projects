from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetInternalHelpdesk(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.base_user_group = self.env.ref("base.group_user")
        self.helpdesk_user_group = self.env.ref("helpdesk.group_helpdesk_user")
        self.helpdesk_manager_group = self.env.ref("helpdesk.group_helpdesk_manager")
        self.tenenet_helpdesk_user_group = self.env.ref("tenenet_projects.group_tenenet_helpdesk_user")
        self.tenenet_helpdesk_editor_group = self.env.ref("tenenet_projects.group_tenenet_helpdesk_editor")
        self.tenenet_helpdesk_manager_group = self.env.ref("tenenet_projects.group_tenenet_helpdesk_manager")

        self.top_user = self._create_user("internal_top", [self.tenenet_helpdesk_user_group.id])
        self.grand_manager_user = self._create_user("internal_grand", [self.tenenet_helpdesk_user_group.id])
        self.manager_user = self._create_user("internal_manager", [self.tenenet_helpdesk_user_group.id])
        self.requester_user = self._create_user("internal_requester", [self.tenenet_helpdesk_user_group.id])
        self.outsider_user = self._create_user("internal_outsider", [self.tenenet_helpdesk_user_group.id])
        self.editor_user = self._create_user("internal_editor", [self.tenenet_helpdesk_editor_group.id])
        self.helpdesk_manager_user = self._create_user("internal_helpdesk_manager", [self.tenenet_helpdesk_manager_group.id])
        self.no_role_user = self._create_user("internal_no_role", [self.helpdesk_user_group.id])

        self.top_employee = self.env["hr.employee"].create({
            "name": "Top Manager",
            "user_id": self.top_user.id,
            "company_id": self.company.id,
        })
        self.grand_manager_employee = self.env["hr.employee"].create({
            "name": "Grand Manager",
            "user_id": self.grand_manager_user.id,
            "parent_id": self.top_employee.id,
            "company_id": self.company.id,
        })
        self.manager_employee = self.env["hr.employee"].create({
            "name": "Direct Manager",
            "user_id": self.manager_user.id,
            "parent_id": self.grand_manager_employee.id,
            "company_id": self.company.id,
        })
        self.requester_employee = self.env["hr.employee"].create({
            "name": "Requester",
            "user_id": self.requester_user.id,
            "parent_id": self.manager_employee.id,
            "company_id": self.company.id,
        })
        self.env["hr.employee"].create({
            "name": "Outsider",
            "user_id": self.outsider_user.id,
            "company_id": self.company.id,
        })
        self.env["hr.employee"].create({
            "name": "Editor",
            "user_id": self.editor_user.id,
            "company_id": self.company.id,
        })
        self.env["hr.employee"].create({
            "name": "Helpdesk Manager",
            "user_id": self.helpdesk_manager_user.id,
            "company_id": self.company.id,
        })
        self.extra_employee = self.env["hr.employee"].create({
            "name": "Extra Employee",
            "company_id": self.company.id,
        })
        self.helpdesk_department = self.env["hr.department"].create({
            "name": "Helpdesk Department",
            "company_id": self.company.id,
        })
        (self.manager_employee | self.grand_manager_employee).write({
            "department_id": self.helpdesk_department.id,
        })

        self.internal_team = self.env["helpdesk.team"].create({
            "name": "Interné TENENET",
            "company_id": self.company.id,
            "privacy_visibility": "internal",
            "member_ids": [
                Command.set([
                    self.requester_user.id,
                    self.manager_user.id,
                    self.grand_manager_user.id,
                    self.top_user.id,
                    self.outsider_user.id,
                    self.editor_user.id,
                    self.helpdesk_manager_user.id,
                ])
            ],
        })
        self.open_stage = self.internal_team.stage_ids.filtered(lambda stage: not stage.fold)[:1]
        self.other_open_stage = self.env["helpdesk.stage"].create({
            "name": "Čaká",
            "sequence": 50,
            "team_ids": [Command.link(self.internal_team.id)],
        })
        self.internal_team.write({
            "stage_ids": [Command.set((self.internal_team.stage_ids | self.other_open_stage).ids)],
        })

    def _create_user(self, login, group_ids):
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": login,
            "login": login,
            "email": f"{login}@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.base_user_group.id, *group_ids])],
        })

    def _create_ticket(self, user, **extra_vals):
        vals = {
            "name": "Interný ticket",
            "team_id": self.internal_team.id,
            "stage_id": self.open_stage.id,
        }
        vals.update(extra_vals)
        return self.env["helpdesk.ticket"].with_user(user).create(vals)

    def _create_subtask(self, ticket, user, **extra_vals):
        vals = {
            "ticket_id": ticket.id,
            "name": "Čiastková úloha",
            "employee_ids": [Command.set([self.manager_employee.id])],
        }
        vals.update(extra_vals)
        return self.env["tenenet.helpdesk.subtask"].with_user(user).create(vals)

    def test_tenenet_helpdesk_role_syncs_real_helpdesk_role(self):
        user = self._create_user("internal_helpdesk_sync", [])

        user.write({"group_ids": [Command.link(self.tenenet_helpdesk_user_group.id)]})
        self.assertIn(self.helpdesk_user_group, user.group_ids)
        self.assertNotIn(self.helpdesk_manager_group, user.group_ids)

        user.write({
            "group_ids": [
                Command.unlink(self.tenenet_helpdesk_user_group.id),
                Command.link(self.tenenet_helpdesk_manager_group.id),
            ],
        })
        self.assertIn(self.helpdesk_manager_group, user.group_ids)

        user.write({
            "group_ids": [
                Command.unlink(self.tenenet_helpdesk_manager_group.id),
                Command.link(self.tenenet_helpdesk_editor_group.id),
            ],
        })
        self.assertIn(self.helpdesk_user_group, user.group_ids)
        self.assertNotIn(self.helpdesk_manager_group, user.group_ids)

        user.write({"group_ids": [Command.unlink(self.tenenet_helpdesk_editor_group.id)]})
        self.assertNotIn(self.helpdesk_user_group, user.group_ids)

    def test_internal_ticket_defaults_requester_and_assignee_to_creator(self):
        ticket = self._create_ticket(self.requester_user)

        self.assertEqual(ticket.tenenet_requested_by_user_id, self.requester_user)
        self.assertEqual(ticket.user_id, self.requester_user)
        self.assertEqual(ticket.tenenet_mass_assigned_employee_ids, self.requester_employee)

    def test_internal_ticket_create_requires_tenenet_helpdesk_role(self):
        with self.assertRaises(AccessError):
            self._create_ticket(self.no_role_user)

    def test_internal_ticket_assignment_cap_on_create_and_write(self):
        ticket = self._create_ticket(self.requester_user, user_id=self.manager_user.id)
        self.assertEqual(ticket.user_id, self.manager_user)

        ticket.write({"user_id": self.grand_manager_user.id})
        self.assertEqual(ticket.user_id, self.grand_manager_user)

        with self.assertRaises(ValidationError):
            self._create_ticket(self.requester_user, user_id=self.top_user.id)

        with self.assertRaises(ValidationError):
            ticket.write({"user_id": self.outsider_user.id})

    def test_followup_and_control_users_respect_assignment_cap(self):
        followup_ticket = self._create_ticket(self.requester_user)
        followup_ticket.write({
            "kanban_state": "blocked",
            "tenenet_followup_user_id": self.manager_user.id,
        })
        self.assertEqual(followup_ticket.tenenet_followup_user_id, self.manager_user)

        with self.assertRaises(ValidationError):
            self._create_ticket(self.requester_user).write({
                "kanban_state": "blocked",
                "tenenet_followup_user_id": self.top_user.id,
            })

        control_ticket = self._create_ticket(self.requester_user)
        control_ticket.write({
            "kanban_state": "done",
            "tenenet_control_user_id": self.grand_manager_user.id,
        })
        self.assertEqual(control_ticket.tenenet_control_user_id, self.grand_manager_user)

        with self.assertRaises(ValidationError):
            self._create_ticket(self.requester_user).write({
                "kanban_state": "done",
                "tenenet_control_user_id": self.outsider_user.id,
            })

    def test_followup_wizard_keeps_main_assignee_and_adds_secondary_assignee(self):
        ticket = self._create_ticket(self.requester_user)
        wizard = self.env["tenenet.helpdesk.ticket.state.wizard"].with_user(self.requester_user).with_context(
            default_ticket_id=ticket.id,
            default_request_type="followup",
            active_id=ticket.id,
            active_model="helpdesk.ticket",
        ).create({
            "ticket_id": ticket.id,
            "request_type": "followup",
            "user_id": self.manager_user.id,
        })

        wizard.action_confirm()

        self.assertEqual(ticket.user_id, self.requester_user)
        self.assertEqual(ticket.tenenet_followup_user_id, self.manager_user)
        self.assertEqual(ticket.kanban_state, "blocked")
        self.assertEqual(
            set(ticket.tenenet_active_assigned_user_ids.ids),
            {self.requester_user.id, self.manager_user.id},
        )
        self.assertEqual(
            self.env["helpdesk.ticket"].search_count([
                ("id", "=", ticket.id),
                ("tenenet_active_assigned_user_ids", "in", self.manager_user.id),
            ]),
            1,
        )

    def test_regular_user_write_access_matrix(self):
        ticket = self._create_ticket(self.requester_user, user_id=self.manager_user.id)

        ticket.with_user(self.requester_user).write({"name": "Requester edit"})
        ticket.with_user(self.manager_user).write({"name": "Assignee edit"})
        ticket.with_user(self.grand_manager_user).write({"name": "Hierarchy edit"})

        with self.assertRaises(AccessError):
            ticket.with_user(self.outsider_user).write({"name": "Denied edit"})

        ticket.message_subscribe(partner_ids=[self.outsider_user.partner_id.id])
        ticket.with_user(self.outsider_user).write({"name": "Follower edit"})
        self.assertEqual(ticket.name, "Follower edit")

    def test_editor_can_edit_but_cannot_delete_or_bypass_assignment_cap(self):
        ticket = self._create_ticket(self.requester_user)

        ticket.with_user(self.editor_user).write({"name": "Editor edit"})
        self.assertEqual(ticket.name, "Editor edit")

        with self.assertRaises(ValidationError):
            ticket.with_user(self.editor_user).write({"user_id": self.top_user.id})

        with self.assertRaises(AccessError):
            ticket.with_user(self.editor_user).unlink()

    def test_helpdesk_manager_can_delete_and_bypass_gate(self):
        ticket = self._create_ticket(self.requester_user)
        ticket.write({
            "kanban_state": "blocked",
            "tenenet_followup_user_id": self.manager_user.id,
        })

        ticket.with_user(self.helpdesk_manager_user).write({
            "kanban_state": "normal",
            "stage_id": self.other_open_stage.id,
        })
        self.assertEqual(ticket.kanban_state, "normal")
        self.assertEqual(ticket.stage_id, self.other_open_stage)

        managed_ticket = self._create_ticket(self.requester_user)
        managed_ticket.with_user(self.helpdesk_manager_user).unlink()
        self.assertFalse(managed_ticket.exists())

    def test_followup_confirmation_gate_and_action(self):
        ticket = self._create_ticket(self.requester_user)
        ticket.write({
            "kanban_state": "blocked",
            "tenenet_followup_user_id": self.manager_user.id,
        })

        with self.assertRaises(UserError):
            ticket.with_user(self.requester_user).write({"stage_id": self.other_open_stage.id})

        with self.assertRaises(UserError):
            ticket.with_user(self.requester_user).write({"kanban_state": "normal"})

        with self.assertRaises(AccessError):
            ticket.with_user(self.outsider_user).action_tenenet_confirm_followup()

        ticket.with_user(self.manager_user).action_tenenet_confirm_followup()
        self.assertEqual(ticket.kanban_state, "normal")
        self.assertEqual(ticket.tenenet_followup_confirmed_by_user_id, self.manager_user)
        self.assertTrue(ticket.tenenet_followup_confirmed_at)

    def test_control_confirmation_gate_and_action(self):
        ticket = self._create_ticket(self.requester_user)
        ticket.write({
            "kanban_state": "done",
            "tenenet_control_user_id": self.manager_user.id,
        })

        with self.assertRaises(UserError):
            ticket.with_user(self.requester_user).write({"kanban_state": "normal"})

        with self.assertRaises(AccessError):
            ticket.with_user(self.outsider_user).action_tenenet_confirm_control()

        ticket.with_user(self.manager_user).action_tenenet_confirm_control()
        self.assertEqual(ticket.kanban_state, "normal")
        self.assertEqual(ticket.tenenet_control_confirmed_by_user_id, self.manager_user)
        self.assertTrue(ticket.tenenet_control_confirmed_at)

    def test_subtask_owner_create_adds_active_assignee(self):
        ticket = self._create_ticket(self.requester_user)
        subtask = self._create_subtask(ticket, self.requester_user)

        self.assertEqual(subtask.ticket_id, ticket)
        self.assertIn(subtask, ticket.tenenet_subtask_ids)
        self.assertEqual(subtask.employee_ids, self.manager_employee)
        self.assertIn(self.manager_user, ticket.tenenet_active_assigned_user_ids)
        self.assertEqual(ticket.tenenet_open_subtask_count, 1)
        self.assertEqual(ticket.tenenet_done_subtask_count, 0)

    def test_subtask_owner_can_assign_multiple_employees(self):
        ticket = self._create_ticket(self.requester_user)

        subtask = self._create_subtask(
            ticket,
            self.requester_user,
            employee_ids=[Command.set([self.manager_employee.id, self.grand_manager_employee.id])],
        )

        self.assertEqual(subtask.employee_ids, self.manager_employee | self.grand_manager_employee)
        self.assertIn(self.manager_user, ticket.tenenet_active_assigned_user_ids)
        self.assertIn(self.grand_manager_user, ticket.tenenet_active_assigned_user_ids)

        subtask.with_user(self.grand_manager_user).write({"is_done": True})
        self.assertTrue(subtask.is_done)

    def test_done_subtask_is_removed_from_active_assignees(self):
        ticket = self._create_ticket(self.requester_user)
        subtask = self._create_subtask(ticket, self.requester_user)

        subtask.with_user(self.manager_user).write({"is_done": True})

        self.assertNotIn(self.manager_user, ticket.tenenet_active_assigned_user_ids)
        self.assertEqual(ticket.tenenet_open_subtask_count, 0)
        self.assertEqual(ticket.tenenet_done_subtask_count, 1)
        self.assertEqual(subtask.done_by_user_id, self.manager_user)
        self.assertTrue(subtask.done_date)

    def test_subtask_assignee_can_change_only_done_checkbox(self):
        ticket = self._create_ticket(self.requester_user)
        subtask = self._create_subtask(ticket, self.requester_user)

        subtask.with_user(self.manager_user).write({"is_done": True})
        self.assertTrue(subtask.is_done)

        with self.assertRaises(AccessError):
            subtask.with_user(self.manager_user).write({"name": "Denied"})
        with self.assertRaises(AccessError):
            subtask.with_user(self.manager_user).write({"description": "<p>Denied</p>"})
        with self.assertRaises(AccessError):
            subtask.with_user(self.manager_user).write({"employee_ids": [Command.set([self.grand_manager_employee.id])]})
        with self.assertRaises(AccessError):
            subtask.with_user(self.manager_user).write({"date_deadline": "2026-04-30"})
        with self.assertRaises(AccessError):
            subtask.with_user(self.manager_user).write({"priority": "2"})
        with self.assertRaises(AccessError):
            subtask.with_user(self.manager_user).unlink()

    def test_subtask_owner_can_edit_content_and_delete(self):
        ticket = self._create_ticket(self.requester_user)
        subtask = self._create_subtask(ticket, self.requester_user)

        subtask.with_user(self.requester_user).write({
            "name": "Owner edit",
            "description": "<p>Owner note</p>",
            "date_deadline": "2026-04-30",
            "employee_ids": [Command.set([self.extra_employee.id])],
            "priority": "2",
        })

        self.assertEqual(subtask.name, "Owner edit")
        self.assertEqual(subtask.employee_ids, self.extra_employee)
        self.assertEqual(subtask.priority, "2")
        subtask.with_user(self.requester_user).unlink()
        self.assertFalse(subtask.exists())

    def test_subtask_helpdesk_manager_can_manage_all_fields(self):
        ticket = self._create_ticket(self.requester_user)
        subtask = self._create_subtask(ticket, self.requester_user)

        subtask.with_user(self.helpdesk_manager_user).write({
            "name": "Manager edit",
            "is_done": True,
        })

        self.assertEqual(subtask.name, "Manager edit")
        self.assertTrue(subtask.is_done)
        subtask.with_user(self.helpdesk_manager_user).unlink()
        self.assertFalse(subtask.exists())

    def test_subtask_outsider_cannot_create_write_or_delete(self):
        ticket = self._create_ticket(self.requester_user)
        subtask = self._create_subtask(ticket, self.requester_user)

        with self.assertRaises(AccessError):
            self._create_subtask(ticket, self.outsider_user)
        with self.assertRaises(AccessError):
            subtask.with_user(self.outsider_user).write({"is_done": True})
        with self.assertRaises(AccessError):
            subtask.with_user(self.outsider_user).unlink()

    def test_subtask_owner_can_assign_any_active_company_employee(self):
        ticket = self._create_ticket(self.requester_user)

        subtask = self._create_subtask(
            ticket,
            self.requester_user,
            employee_ids=[Command.set([self.extra_employee.id])],
        )

        self.assertEqual(subtask.employee_ids, self.extra_employee)
        self.assertNotIn(self.extra_employee.user_id, ticket.tenenet_active_assigned_user_ids)

    def test_subtask_leaving_done_clears_done_metadata(self):
        ticket = self._create_ticket(self.requester_user)
        subtask = self._create_subtask(ticket, self.requester_user)

        subtask.with_user(self.manager_user).write({"is_done": True})
        self.assertTrue(subtask.done_by_user_id)
        self.assertTrue(subtask.done_date)

        subtask.with_user(self.manager_user).write({"is_done": False})

        self.assertFalse(subtask.done_by_user_id)
        self.assertFalse(subtask.done_date)

    def test_mass_ticket_wizard_creates_ticket_for_department_employees(self):
        wizard = self.env["tenenet.helpdesk.mass.ticket.wizard"].with_user(self.helpdesk_manager_user).create({
            "name": "Hromadný test",
            "team_id": self.internal_team.id,
            "target_type": "department",
            "department_id": self.helpdesk_department.id,
            "description": "<p>Test</p>",
            "date_deadline": "2026-04-30",
        })

        self.assertEqual(set(wizard.employee_ids.ids), {self.manager_employee.id, self.grand_manager_employee.id})
        action = wizard.action_create_ticket()
        ticket = self.env["helpdesk.ticket"].browse(action["res_id"])

        self.assertEqual(action["res_model"], "helpdesk.ticket")
        self.assertEqual(action["view_mode"], "form")
        self.assertEqual(ticket.name, "Hromadný test")
        self.assertEqual(ticket.team_id, self.internal_team)
        self.assertEqual(ticket.tenenet_requested_by_user_id, self.helpdesk_manager_user)
        self.assertEqual(str(ticket.tenenet_date_deadline), "2026-04-30")
        self.assertFalse(ticket.tenenet_subtask_ids)
        self.assertEqual(
            set(ticket.tenenet_mass_assigned_employee_ids.ids),
            {self.manager_employee.id, self.grand_manager_employee.id},
        )
        self.assertEqual(
            set(ticket.tenenet_mass_assigned_user_ids.ids),
            {self.manager_user.id, self.grand_manager_user.id},
        )
        self.assertIn(self.manager_user, ticket.tenenet_active_assigned_user_ids)
        self.assertIn(self.grand_manager_user, ticket.tenenet_active_assigned_user_ids)

    def test_mass_ticket_wizard_project_uses_project_assignment_employees(self):
        admin_program = self.env.ref("tenenet_projects.tenenet_program_admin_tenenet")
        project = self.env["tenenet.project"].create({
            "name": "Helpdesk project",
            "program_ids": [Command.set(admin_program.ids)],
        })
        self.env["tenenet.project.assignment"].create({
            "project_id": project.id,
            "employee_id": self.manager_employee.id,
            "allocation_ratio": 100.0,
        })
        self.env["tenenet.project.assignment"].create({
            "project_id": project.id,
            "employee_id": self.extra_employee.id,
            "allocation_ratio": 100.0,
        })

        wizard = self.env["tenenet.helpdesk.mass.ticket.wizard"].with_user(self.helpdesk_manager_user).create({
            "name": "Projektový hromadný test",
            "team_id": self.internal_team.id,
            "target_type": "project",
            "project_id": project.id,
        })

        self.assertEqual(set(wizard.employee_ids.ids), {self.manager_employee.id, self.extra_employee.id})
        action = wizard.action_create_ticket()
        ticket = self.env["helpdesk.ticket"].browse(action["res_id"])

        self.assertFalse(ticket.tenenet_subtask_ids)
        self.assertEqual(set(ticket.tenenet_mass_assigned_employee_ids.ids), {self.manager_employee.id, self.extra_employee.id})
        self.assertEqual(ticket.tenenet_mass_assigned_user_ids, self.manager_user)
        self.assertIn(self.manager_user, ticket.tenenet_active_assigned_user_ids)
