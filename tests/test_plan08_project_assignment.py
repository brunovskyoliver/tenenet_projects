from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan08ProjectAssignment(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({
            "name": "Zamestnanec Priradenie",
            "work_ratio": 100.0,
        })
        self.employee2 = self.env["hr.employee"].create({"name": "Zamestnanec 2 Priradenie"})
        self.admin_program = self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1)
        self.project = self.env["tenenet.project"].create({
            "name": "Testovací projekt",
            "program_ids": [Command.set(self.admin_program.ids)],
            "reporting_program_id": self.admin_program.id,
        })
        self.project2 = self.env["tenenet.project"].create({
            "name": "Testovací projekt 2",
            "program_ids": [Command.set(self.admin_program.ids)],
            "reporting_program_id": self.admin_program.id,
        })
        self.company = self.env.company
        base_user_group = self.env.ref("base.group_user")
        tenenet_user_group = self.env.ref("tenenet_projects.group_tenenet_user")
        tenenet_manager_group = self.env.ref("tenenet_projects.group_tenenet_manager")

        self.user_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Použ. Priradenie",
                "login": "assignment_user",
                "email": "assignment_user@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([base_user_group.id, tenenet_user_group.id])],
            }
        )
        self.manager_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Manažér Priradenie",
                "login": "assignment_manager",
                "email": "assignment_manager@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([base_user_group.id, tenenet_manager_group.id])],
            }
        )

    def _assignment_vals(self, **overrides):
        vals = {
            "employee_id": self.employee.id,
            "project_id": self.project.id,
            "allocation_ratio": 100.0,
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        }
        vals.update(overrides)
        return vals

    def test_assignment_creates_successfully(self):
        assignment = self.env["tenenet.project.assignment"].create(self._assignment_vals())
        self.assertTrue(assignment.active)
        self.assertEqual(assignment.employee_id, self.employee)
        self.assertEqual(assignment.project_id, self.project)
        self.assertAlmostEqual(assignment.allocation_ratio, 100.0)
        self.assertFalse(assignment.settlement_only)
        self.assertAlmostEqual(assignment.wage_hm, 10.0)
        self.assertAlmostEqual(assignment.wage_ccp, 13.62)

    def test_assignment_can_be_marked_settlement_only(self):
        assignment = self.env["tenenet.project.assignment"].create(
            self._assignment_vals(settlement_only=True)
        )
        self.assertTrue(assignment.settlement_only)

    def test_assignment_wizard_view_contains_settlement_only_field(self):
        arch = self.env["tenenet.project.assignment.wizard"].get_view(
            view_id=self.env.ref("tenenet_projects.view_tenenet_project_assignment_wizard_form").id,
            view_type="form",
        )["arch"]
        self.assertIn('name="settlement_only"', arch)

    def test_project_assignment_views_contain_settlement_only_field(self):
        project_arch = self.env["tenenet.project"].get_view(
            view_id=self.env.ref("tenenet_projects.view_tenenet_project_form").id,
            view_type="form",
        )["arch"]
        assignment_arch = self.env["tenenet.project.assignment"].get_view(
            view_id=self.env.ref("tenenet_projects.view_tenenet_project_assignment_form").id,
            view_type="form",
        )["arch"]

        self.assertIn('name="settlement_only"', project_arch)
        self.assertIn('name="settlement_only"', assignment_arch)

    def test_assignment_form_contains_ratio_planner(self):
        assignment_arch = self.env["tenenet.project.assignment"].get_view(
            view_id=self.env.ref("tenenet_projects.view_tenenet_project_assignment_form").id,
            view_type="form",
        )["arch"]

        self.assertIn('name="ratio_planner_state"', assignment_arch)
        self.assertIn('widget="tenenet_assignment_ratio_planner"', assignment_arch)

    def test_monthly_ratio_overrides_scalar_fallback(self):
        assignment = self.env["tenenet.project.assignment"].create(self._assignment_vals(allocation_ratio=50.0))
        ratio_month = self.env["tenenet.project.assignment.ratio.month"].create({
            "assignment_id": assignment.id,
            "period": "2026-01-15",
            "allocation_ratio": 25.0,
        })

        self.assertEqual(ratio_month.period.isoformat(), "2026-01-01")
        self.assertAlmostEqual(assignment._get_effective_allocation_ratio("2026-01-01"), 25.0)
        self.assertAlmostEqual(assignment._get_effective_allocation_ratio("2026-02-01"), 50.0)

    def test_monthly_ratio_allows_explicit_zero(self):
        assignment = self.env["tenenet.project.assignment"].create(self._assignment_vals(allocation_ratio=50.0))

        assignment.set_month_ratios(2026, {"1": 0.0})

        self.assertAlmostEqual(assignment._get_effective_allocation_ratio("2026-01-01"), 0.0)
        self.assertAlmostEqual(assignment._get_effective_allocation_ratio("2026-02-01"), 50.0)

    def test_duplicate_monthly_ratio_rejected(self):
        assignment = self.env["tenenet.project.assignment"].create(self._assignment_vals(allocation_ratio=50.0))
        self.env["tenenet.project.assignment.ratio.month"].create({
            "assignment_id": assignment.id,
            "period": "2026-01-01",
            "allocation_ratio": 25.0,
        })

        with self.cr.savepoint():
            with self.assertRaises(IntegrityError):
                self.env["tenenet.project.assignment.ratio.month"].create({
                    "assignment_id": assignment.id,
                    "period": "2026-01-20",
                    "allocation_ratio": 30.0,
                })

    def test_monthly_ratio_capacity_rejects_overallocated_month(self):
        self.env["tenenet.project.assignment"].create(self._assignment_vals(allocation_ratio=60.0))
        second = self.env["tenenet.project.assignment"].create(
            self._assignment_vals(project_id=self.project2.id, allocation_ratio=40.0)
        )

        with self.assertRaises(ValidationError):
            second.set_month_ratios(2026, {"1": 50.0})

    def test_non_overlapping_monthly_ratios_can_exceed_across_time(self):
        first = self.env["tenenet.project.assignment"].create(
            self._assignment_vals(
                allocation_ratio=100.0,
                date_start="2026-01-01",
                date_end="2026-06-30",
            )
        )
        second = self.env["tenenet.project.assignment"].create(
            self._assignment_vals(
                project_id=self.project2.id,
                allocation_ratio=100.0,
                date_start="2026-07-01",
                date_end="2026-12-31",
            )
        )
        first.set_month_ratios(2026, {"1": 100.0})
        second.set_month_ratios(2026, {"7": 100.0})

        self.assertAlmostEqual(first._get_effective_allocation_ratio("2026-01-01"), 100.0)
        self.assertAlmostEqual(second._get_effective_allocation_ratio("2026-07-01"), 100.0)

    def test_ratio_planner_payload_contains_expected_keys(self):
        assignment = self.env["tenenet.project.assignment"].create(self._assignment_vals(allocation_ratio=50.0))
        assignment.set_month_ratios(2026, {"1": 25.0})

        data = assignment.get_ratio_planner_data(2026)

        self.assertEqual(data["fallback_ratio"], 50.0)
        self.assertEqual(data["months"]["1"], 25.0)
        self.assertEqual(data["months"]["2"], 50.0)
        self.assertIn(1, data["explicit_months"])
        self.assertIn(2026, data["available_years"])

    def test_non_overlapping_same_project_periods_are_allowed(self):
        a1 = self.env["tenenet.project.assignment"].create(
            self._assignment_vals(date_start="2026-01-01", date_end="2026-03-31")
        )
        a2 = self.env["tenenet.project.assignment"].create(
            self._assignment_vals(date_start="2026-04-01", date_end="2026-12-31")
        )
        self.assertTrue(a1.exists())
        self.assertTrue(a2.exists())

    def test_different_projects_allowed_when_capacity_allows(self):
        a1 = self.env["tenenet.project.assignment"].create(self._assignment_vals())
        self.employee.write({"work_ratio": 200.0})
        a2 = self.env["tenenet.project.assignment"].create(self._assignment_vals(project_id=self.project2.id))
        self.assertTrue(a1.exists())
        self.assertTrue(a2.exists())

    def test_date_constraint(self):
        with self.assertRaises(ValidationError):
            self.env["tenenet.project.assignment"].create(
                self._assignment_vals(date_start="2026-06-01", date_end="2026-01-01")
            )

    def test_overlapping_assignments_above_employee_capacity_are_rejected(self):
        self.env["tenenet.project.assignment"].create(
            self._assignment_vals(
                allocation_ratio=60.0,
                date_start="2026-01-01",
                date_end="2026-06-30",
            )
        )
        with self.assertRaises(ValidationError):
            self.env["tenenet.project.assignment"].create(
                self._assignment_vals(
                    project_id=self.project2.id,
                    allocation_ratio=50.0,
                    date_start="2026-06-15",
                    date_end="2026-12-31",
                )
            )

    def test_non_overlapping_assignments_can_exceed_capacity_across_time(self):
        first = self.env["tenenet.project.assignment"].create(
            self._assignment_vals(
                allocation_ratio=100.0,
                date_start="2026-01-01",
                date_end="2026-06-30",
            )
        )
        second = self.env["tenenet.project.assignment"].create(
            self._assignment_vals(
                project_id=self.project2.id,
                allocation_ratio=100.0,
                date_start="2026-07-01",
                date_end="2026-12-31",
            )
        )
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

    def test_allocation_ratio_constraint(self):
        with self.assertRaises(ValidationError):
            self.env["tenenet.project.assignment"].create(self._assignment_vals(allocation_ratio=0.0))
        with self.assertRaises(ValidationError):
            self.env["tenenet.project.assignment"].create(self._assignment_vals(allocation_ratio=101.0))

    def test_assignment_on_employee_one2many(self):
        self.env["tenenet.project.assignment"].create(self._assignment_vals())
        self.employee.invalidate_recordset()
        self.assertEqual(len(self.employee.assignment_ids), 1)

    def test_assignment_on_project_one2many(self):
        self.env["tenenet.project.assignment"].create(self._assignment_vals())
        self.project.invalidate_recordset()
        self.assertEqual(len(self.project.assignment_ids), 1)

    def test_acl_user_read_only_manager_full(self):
        with self.assertRaises(AccessError):
            self.env["tenenet.project.assignment"].with_user(self.user_user).create(
                self._assignment_vals()
            )
        assignment = self.env["tenenet.project.assignment"].with_user(self.manager_user).create(
            self._assignment_vals()
        )
        self.assertTrue(assignment.exists())

    def test_remove_wizard_action_opens_for_assignment(self):
        assignment = self.env["tenenet.project.assignment"].create(self._assignment_vals())

        action = assignment.action_open_remove_wizard()

        self.assertEqual(action["res_model"], "tenenet.project.assignment.remove.wizard")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["context"]["default_assignment_id"], assignment.id)

    def test_remove_wizard_can_archive_assignment(self):
        assignment = self.env["tenenet.project.assignment"].create(self._assignment_vals())
        wizard = self.env["tenenet.project.assignment.remove.wizard"].create({
            "assignment_id": assignment.id,
        })

        wizard.action_archive_assignment()
        assignment.invalidate_recordset(["active", "state"])

        self.assertFalse(assignment.active)
        self.assertEqual(assignment.state, "finished")

    def test_remove_wizard_can_delete_assignment(self):
        assignment = self.env["tenenet.project.assignment"].create(self._assignment_vals())
        wizard = self.env["tenenet.project.assignment.remove.wizard"].create({
            "assignment_id": assignment.id,
        })

        wizard.action_delete_assignment()

        self.assertFalse(assignment.exists())

    def test_leave_rule_creates_successfully(self):
        leave_type = self.env["hr.leave.type"].create({
            "name": "Dovolenka test",
            "requires_allocation": False,
        })
        rule = self.env["tenenet.project.leave.rule"].create({
            "project_id": self.project.id,
            "leave_type_id": leave_type.id,
            "included": True,
        })
        self.assertTrue(rule.included)

    def test_leave_rule_unique_constraint(self):
        leave_type = self.env["hr.leave.type"].create({
            "name": "Dovolenka test2",
            "requires_allocation": False,
        })
        self.env["tenenet.project.leave.rule"].create({
            "project_id": self.project.id,
            "leave_type_id": leave_type.id,
            "included": True,
        })
        with self.cr.savepoint():
            with self.assertRaises(IntegrityError):
                self.env["tenenet.project.leave.rule"].create({
                    "project_id": self.project.id,
                    "leave_type_id": leave_type.id,
                    "included": False,
                })
