from datetime import date

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetProjectAssignmentWizard(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({
            "name": "Wizard Employee",
            "work_ratio": 100.0,
        })
        self.program = self.env["tenenet.program"].create({
            "name": "Wizard Program",
            "code": "WIZARD_PRG",
        })
        self.project = self.env["tenenet.project"].create({
            "name": "Wizard Project",
            "program_ids": [(6, 0, self.program.ids)],
            "reporting_program_id": self.program.id,
        })
        self.assignment_model = self.env["tenenet.project.assignment"]
        self.wizard_model = self.env["tenenet.project.assignment.wizard"]
        self.today = fields.Date.context_today(self.wizard_model)

    def _create_assignment(self, project=None, **overrides):
        project = project or self.project
        vals = {
            "employee_id": self.employee.id,
            "project_id": project.id,
            "allocation_ratio": 40.0,
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        }
        vals.update(overrides)
        return self.assignment_model.create(vals)

    def _create_wizard(self, **overrides):
        vals = {
            "project_id": self.project.id,
            "employee_id": self.employee.id,
            "program_id": self.program.id,
        }
        vals.update(overrides)
        return self.wizard_model.create(vals)

    def test_wizard_defaults_to_current_year(self):
        wizard = self.wizard_model.create({
            "project_id": self.project.id,
            "employee_id": self.employee.id,
            "program_id": self.program.id,
        })

        self.assertEqual(wizard.date_start, date(self.today.year, 1, 1))
        self.assertEqual(wizard.date_end, date(self.today.year, 12, 31))

    def test_employee_without_overlaps_shows_full_capacity(self):
        wizard = self._create_wizard(date_start="2026-01-01", date_end="2026-12-31")

        self.assertAlmostEqual(wizard.free_ratio_for_period, 100.0, places=2)

    def test_partial_overlap_reduces_free_capacity(self):
        self._create_assignment(allocation_ratio=35.0, date_start="2026-01-01", date_end="2026-12-31")

        wizard = self._create_wizard(date_start="2026-03-01", date_end="2026-06-30")

        self.assertAlmostEqual(wizard.free_ratio_for_period, 65.0, places=2)

    def test_wizard_uses_lowest_free_capacity_within_span(self):
        project_b = self.env["tenenet.project"].create({
            "name": "Wizard Project B",
            "program_ids": [(6, 0, self.program.ids)],
            "reporting_program_id": self.program.id,
        })
        self._create_assignment(allocation_ratio=20.0, date_start="2026-01-01", date_end="2026-12-31")
        self._create_assignment(
            project=project_b,
            allocation_ratio=50.0,
            date_start="2026-06-01",
            date_end="2026-08-31",
        )

        wizard = self._create_wizard(date_start="2026-01-01", date_end="2026-12-31")

        self.assertAlmostEqual(wizard.free_ratio_for_period, 30.0, places=2)

    def test_non_overlapping_finished_and_future_assignments_are_ignored(self):
        self._create_assignment(allocation_ratio=40.0, date_end="2025-01-31")
        future_project = self.env["tenenet.project"].create({
            "name": "Wizard Future Project",
            "program_ids": [(6, 0, self.program.ids)],
            "reporting_program_id": self.program.id,
        })
        self._create_assignment(
            project=future_project,
            allocation_ratio=25.0,
            date_start="2099-01-01",
        )

        wizard = self._create_wizard(date_start="2026-01-01", date_end="2026-12-31")

        self.assertAlmostEqual(wizard.free_ratio_for_period, 100.0, places=2)

    def test_wizard_free_capacity_matches_assignment_constraint_span_logic(self):
        self._create_assignment(allocation_ratio=60.0, date_start="2026-01-01", date_end="2026-06-30")

        wizard = self._create_wizard(date_start="2026-03-01", date_end="2026-12-31")

        self.assertAlmostEqual(wizard.free_ratio_for_period, 40.0, places=2)
