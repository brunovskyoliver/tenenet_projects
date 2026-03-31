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
        self.project = self.env["tenenet.project"].create({"name": "Testovací projekt"})
        self.project2 = self.env["tenenet.project"].create({"name": "Testovací projekt 2"})
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
        self.assertAlmostEqual(assignment.wage_hm, 10.0)
        self.assertAlmostEqual(assignment.wage_ccp, 13.62)

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
