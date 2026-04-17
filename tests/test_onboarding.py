from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "tenenet_onboarding")
class TestTenenetOnboarding(TransactionCase):
    """Tests for tenenet.onboarding process and related models."""

    def setUp(self):
        super().setUp()
        self.company = self.env.company

        # Groups
        self.helpdesk_user_grp = self.env.ref("helpdesk.group_helpdesk_user")
        self.tnnt_user_grp = self.env.ref("tenenet_projects.group_tenenet_helpdesk_user")
        self.tnnt_editor_grp = self.env.ref("tenenet_projects.group_tenenet_helpdesk_editor")
        self.tnnt_manager_grp = self.env.ref("tenenet_projects.group_tenenet_helpdesk_manager")

        # Users
        self.hr_user = self._create_user("ob_hr_user", [self.tnnt_user_grp.id])
        self.manager_user = self._create_user("ob_manager_user", [self.tnnt_user_grp.id])
        self.editor_user = self._create_user("ob_editor_user", [self.tnnt_editor_grp.id])
        self.helpdesk_manager = self._create_user("ob_hd_manager", [self.tnnt_manager_grp.id])
        self.outsider = self._create_user("ob_outsider", [self.tnnt_user_grp.id])

        # Job position
        self.test_job = self.env["hr.job"].create({
            "name": "Testovacia pozícia",
            "company_id": self.company.id,
        })

        # Employees
        self.manager_employee = self.env["hr.employee"].create({
            "name": "Test Manager",
            "user_id": self.manager_user.id,
            "company_id": self.company.id,
        })
        self.new_employee = self.env["hr.employee"].create({
            "name": "Test Nováčik",
            "parent_id": self.manager_employee.id,
            "company_id": self.company.id,
        })
        self.buddy_employee = self.env["hr.employee"].create({
            "name": "Test Buddy",
            "user_id": self.editor_user.id,
            "company_id": self.company.id,
        })

        # Helpdesk team
        self.team = self.env["helpdesk.team"].create({
            "name": "Interné TENENET",
            "company_id": self.company.id,
            "privacy_visibility": "internal",
            "member_ids": [Command.set([
                self.hr_user.id,
                self.manager_user.id,
                self.editor_user.id,
                self.helpdesk_manager.id,
            ])],
        })

        # Seed a few task templates
        self.templates = self._seed_templates()

    def _create_user(self, login, group_ids):
        base_group = self.env.ref("base.group_user")
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": login,
            "login": login,
            "email": f"{login}@test.com",
            "group_ids": [Command.set([base_group.id, *group_ids])],
            "company_ids": [Command.set([self.company.id])],
            "company_id": self.company.id,
        })

    def _seed_templates(self):
        """Create minimal task templates for testing."""
        return self.env["tenenet.onboarding.task.template"].create([
            {
                "name": "Komunikovať s kandidátom",
                "phase": "pre_hire",
                "sequence": 10,
                "responsible_role": "hr",
                "is_mandatory": True,
            },
            {
                "name": "Pripraviť pracovnú zmluvu",
                "phase": "pre_hire",
                "sequence": 20,
                "responsible_role": "hr",
                "is_mandatory": True,
            },
            {
                "name": "BOZP školenie",
                "phase": "day_one",
                "sequence": 10,
                "responsible_role": "hr",
                "is_mandatory": True,
            },
            {
                "name": "Predstaviť tímu",
                "phase": "day_one",
                "sequence": 20,
                "responsible_role": "manager",
                "is_mandatory": True,
            },
            {
                "name": "Pravidelné check-iny",
                "phase": "first_weeks",
                "sequence": 10,
                "responsible_role": "manager",
                "is_mandatory": True,
            },
            {
                "name": "Projektová úloha",
                "phase": "pre_hire",
                "sequence": 100,
                "responsible_role": "project_manager",
                "is_mandatory": True,
                "project_only": True,
            },
            {
                "name": "Voliteľná úloha",
                "phase": "first_weeks",
                "sequence": 200,
                "responsible_role": "hr",
                "is_mandatory": False,
            },
        ])

    def _create_onboarding(self, **kwargs):
        defaults = {
            "employee_id": self.new_employee.id,
            "job_id": self.test_job.id,
            "hr_user_id": self.hr_user.id,
            "manager_user_id": self.manager_user.id,
            "buddy_employee_id": self.buddy_employee.id,
        }
        defaults.update(kwargs)
        return self.env["tenenet.onboarding"].create(defaults)

    # -------------------------------------------------------------------------
    # Test 1: Task generation from templates
    # -------------------------------------------------------------------------

    def test_task_generation_creates_tasks_from_templates(self):
        ob = self._create_onboarding()
        # All non-project_only templates (including seeded ones) should be generated
        all_non_project = self.env["tenenet.onboarding.task.template"].search([
            ("active", "=", True), ("project_only", "=", False)
        ])
        self.assertEqual(len(ob.task_ids), len(all_non_project))

    def test_task_generation_includes_project_tasks_when_flagged(self):
        ob = self._create_onboarding(project_related=True)
        all_templates = self.env["tenenet.onboarding.task.template"].search([("active", "=", True)])
        self.assertEqual(len(ob.task_ids), len(all_templates))

    def test_task_generation_excludes_project_tasks_by_default(self):
        ob = self._create_onboarding()
        project_tasks = ob.task_ids.filtered(lambda t: t.template_id.project_only)
        self.assertEqual(len(project_tasks), 0)

    def test_task_responsible_user_resolved_from_role(self):
        ob = self._create_onboarding()
        hr_tasks = ob.task_ids.filtered(lambda t: t.responsible_role == "hr")
        for task in hr_tasks:
            self.assertEqual(task.responsible_user_id, self.hr_user)
        mgr_tasks = ob.task_ids.filtered(lambda t: t.responsible_role == "manager")
        for task in mgr_tasks:
            self.assertEqual(task.responsible_user_id, self.manager_user)

    def test_task_phase_sequence_set_correctly(self):
        ob = self._create_onboarding()
        for task in ob.task_ids:
            expected = {"pre_hire": 10, "day_one": 20, "first_weeks": 30}[task.phase]
            self.assertEqual(task.phase_sequence, expected)

    # -------------------------------------------------------------------------
    # Test 2: Helpdesk ticket auto-creation
    # -------------------------------------------------------------------------

    def test_helpdesk_ticket_created_on_onboarding_create(self):
        ob = self._create_onboarding()
        self.assertTrue(ob.helpdesk_ticket_id, "Helpdesk ticket should be auto-created")

    def test_helpdesk_ticket_in_correct_team(self):
        ob = self._create_onboarding()
        self.assertEqual(ob.helpdesk_ticket_id.team_id, self.team)

    def test_helpdesk_ticket_in_onboarding_stage(self):
        ob = self._create_onboarding()
        self.assertEqual(
            ob.helpdesk_ticket_id.stage_id.name,
            "Onboarding",
            "Ticket should be in 'Onboarding' stage",
        )

    def test_helpdesk_ticket_back_link(self):
        ob = self._create_onboarding()
        self.assertEqual(ob.helpdesk_ticket_id.tenenet_onboarding_id, ob)

    def test_helpdesk_ticket_blocked_from_manual_stage_change(self):
        ob = self._create_onboarding()
        ticket = ob.helpdesk_ticket_id
        other_stage = self.env["helpdesk.stage"].create({
            "name": "Iná fáza",
            "team_ids": [Command.link(self.team.id)],
        })
        with self.assertRaises(UserError):
            ticket.write({"stage_id": other_stage.id})

    # -------------------------------------------------------------------------
    # Test 3: Progress computation
    # -------------------------------------------------------------------------

    def test_progress_zero_initially(self):
        ob = self._create_onboarding()
        self.assertEqual(ob.progress, 0.0)
        self.assertEqual(ob.task_done_count, 0)
        self.assertGreater(ob.task_count, 0)

    def test_progress_updates_when_task_done(self):
        ob = self._create_onboarding()
        task = ob.task_ids[0]
        task.write({"state": "done"})
        ob._compute_progress()
        self.assertGreater(ob.progress, 0.0)

    def test_progress_counts_skipped_as_done(self):
        ob = self._create_onboarding()
        task = ob.task_ids[0]
        task.write({"state": "skipped"})
        ob._compute_progress()
        self.assertGreater(ob.task_done_count, 0)

    # -------------------------------------------------------------------------
    # Test 4: Phase transitions
    # -------------------------------------------------------------------------

    def test_phase_starts_at_pre_hire(self):
        ob = self._create_onboarding()
        self.assertEqual(ob.phase, "pre_hire")

    def test_next_phase_blocked_if_mandatory_tasks_incomplete(self):
        ob = self._create_onboarding()
        with self.assertRaises(ValidationError):
            ob.action_next_phase()

    def test_next_phase_advances_when_all_mandatory_done(self):
        ob = self._create_onboarding()
        # Mark all pre_hire mandatory tasks as done
        pre_hire_mandatory = ob.task_ids.filtered(
            lambda t: t.phase == "pre_hire" and t.is_mandatory
        )
        pre_hire_mandatory.write({"state": "done"})
        ob.action_next_phase()
        self.assertEqual(ob.phase, "day_one")

    def test_next_phase_skipped_tasks_count_as_complete(self):
        ob = self._create_onboarding()
        pre_hire_mandatory = ob.task_ids.filtered(
            lambda t: t.phase == "pre_hire" and t.is_mandatory
        )
        pre_hire_mandatory.write({"state": "skipped"})
        ob.action_next_phase()
        self.assertEqual(ob.phase, "day_one")

    def test_previous_phase_requires_editor_or_manager(self):
        ob = self._create_onboarding()
        # Advance to day_one first
        ob.task_ids.filtered(lambda t: t.phase == "pre_hire" and t.is_mandatory).write({"state": "done"})
        ob.action_next_phase()
        self.assertEqual(ob.phase, "day_one")
        # Regular user cannot go back
        with self.assertRaises(UserError):
            ob.with_user(self.hr_user).action_previous_phase()

    def test_previous_phase_allowed_for_editor(self):
        ob = self._create_onboarding()
        ob.task_ids.filtered(lambda t: t.phase == "pre_hire" and t.is_mandatory).write({"state": "done"})
        ob.action_next_phase()
        self.assertEqual(ob.phase, "day_one")
        ob.with_user(self.editor_user).action_previous_phase()
        self.assertEqual(ob.phase, "pre_hire")

    def test_complete_closes_helpdesk_ticket(self):
        ob = self._create_onboarding()
        ticket = ob.helpdesk_ticket_id
        # Create closing stage
        close_stage = self.env["helpdesk.stage"].create({
            "name": "Vyriešené",
            "fold": True,
            "team_ids": [Command.link(self.team.id)],
        })
        self.team.to_stage_id = close_stage.id
        # Complete all tasks
        ob.task_ids.write({"state": "done"})
        ob.task_ids.filtered(lambda t: t.phase == "pre_hire" and t.is_mandatory).write({"state": "done"})
        ob.task_ids.filtered(lambda t: t.phase == "day_one" and t.is_mandatory).write({"state": "done"})
        ob.task_ids.filtered(lambda t: t.phase == "first_weeks" and t.is_mandatory).write({"state": "done"})
        # Navigate to first_weeks
        ob.task_ids.write({"state": "done"})
        ob.write({"phase": "first_weeks"})
        ob.action_complete()
        self.assertEqual(ob.phase, "done")
        self.assertEqual(ticket.stage_id, close_stage)

    # -------------------------------------------------------------------------
    # Test 5: Task completion access control
    # -------------------------------------------------------------------------

    def test_task_done_by_responsible_user(self):
        ob = self._create_onboarding()
        hr_task = ob.task_ids.filtered(lambda t: t.responsible_role == "hr")[0]
        hr_task.with_user(self.hr_user).write({"state": "done"})
        self.assertEqual(hr_task.state, "done")

    def test_task_done_records_user_and_timestamp(self):
        ob = self._create_onboarding()
        hr_task = ob.task_ids.filtered(lambda t: t.responsible_role == "hr")[0]
        hr_task.with_user(self.hr_user).write({"state": "done"})
        self.assertEqual(hr_task.done_by_user_id, self.hr_user)
        self.assertTrue(hr_task.done_date)

    def test_task_done_blocked_for_non_responsible_user(self):
        ob = self._create_onboarding()
        mgr_task = ob.task_ids.filtered(lambda t: t.responsible_role == "manager")[0]
        with self.assertRaises(AccessError):
            mgr_task.with_user(self.outsider).write({"state": "done"})

    def test_task_done_allowed_for_editor_regardless_of_role(self):
        ob = self._create_onboarding()
        mgr_task = ob.task_ids.filtered(lambda t: t.responsible_role == "manager")[0]
        mgr_task.with_user(self.editor_user).write({"state": "done"})
        self.assertEqual(mgr_task.state, "done")

    def test_task_done_allowed_for_helpdesk_manager(self):
        ob = self._create_onboarding()
        mgr_task = ob.task_ids.filtered(lambda t: t.responsible_role == "manager")[0]
        mgr_task.with_user(self.helpdesk_manager).write({"state": "done"})
        self.assertEqual(mgr_task.state, "done")

    # -------------------------------------------------------------------------
    # Test 6: Employee smart button
    # -------------------------------------------------------------------------

    def test_employee_onboarding_count(self):
        ob = self._create_onboarding()
        self.new_employee._compute_tenenet_onboarding_count()
        self.assertEqual(self.new_employee.tenenet_onboarding_count, 1)

    def test_employee_onboarding_state_in_progress(self):
        ob = self._create_onboarding()
        self.new_employee._compute_tenenet_onboarding_state()
        self.assertEqual(self.new_employee.tenenet_onboarding_state, "in_progress")

    def test_employee_onboarding_state_completed(self):
        ob = self._create_onboarding()
        ob.write({"phase": "done"})
        self.new_employee._compute_tenenet_onboarding_state()
        self.assertEqual(self.new_employee.tenenet_onboarding_state, "completed")

    def test_employee_no_onboarding_state_not_started(self):
        self.new_employee._compute_tenenet_onboarding_state()
        self.assertEqual(self.new_employee.tenenet_onboarding_state, "not_started")

    # -------------------------------------------------------------------------
    # Test 7: Template management
    # -------------------------------------------------------------------------

    def test_template_phase_sequence_computed(self):
        self.assertEqual(self.templates[0].phase_sequence, 10)  # pre_hire

    def test_template_manager_can_manage(self):
        """Helpdesk manager should be able to create/edit templates."""
        new_tmpl = self.env["tenenet.onboarding.task.template"].with_user(self.helpdesk_manager).create({
            "name": "Nová šablóna",
            "phase": "day_one",
            "responsible_role": "hr",
        })
        self.assertTrue(new_tmpl.id)

    def test_onboarding_name_computed(self):
        ob = self._create_onboarding()
        self.assertIn("Onboarding", ob.name)
        self.assertIn("Test Nováčik", ob.name)
