from datetime import date
from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHomeMenuUtilizationMetric(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.base_user_group = self.env.ref("base.group_user")
        self.tenenet_user_group = self.env.ref("tenenet_projects.group_tenenet_user")
        self.donor = self.env["tenenet.donor"].create({
            "name": "Donor pre home widget",
            "donor_type": "sr_ministerstvo",
        })
        self.project = self.env["tenenet.project"].create({
            "name": "Projekt home widget",
            "donor_id": self.donor.id,
        })
        self.user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Používateľ Home Widget",
            "login": "home_widget_user",
            "email": "home_widget_user@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.base_user_group.id, self.tenenet_user_group.id])],
        })
        self.employee = self.env["hr.employee"].create({
            "name": "Home Widget Zamestnanec",
            "user_id": self.user.id,
            "work_ratio": 100.0,
        })
        self.assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.project.id,
            "allocation_ratio": 100.0,
            "date_start": "2025-01-01",
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        })

    def _previous_period(self):
        current_month_start = fields.Date.context_today(self.env.user).replace(day=1)
        return (current_month_start + relativedelta(months=-1)).replace(day=1)

    def _create_previous_month_timesheet(self, **hours):
        period = self._previous_period()
        timesheet = self.env["tenenet.project.timesheet"]._get_or_create_for_assignment_period(
            self.assignment,
            period,
        )
        if hours:
            timesheet.with_context(from_hr_leave_sync=True).write(hours)
        self.env["tenenet.utilization"]._refresh_for_period(period, employee_ids=[self.employee.id])
        return period

    def test_returns_metric_for_linked_user_with_previous_month_utilization(self):
        previous_period = self._create_previous_month_timesheet(
            hours_pp=80.0,
            hours_np=8.0,
            hours_training=4.0,
        )

        payload = self.env["res.users"].with_user(self.user).get_home_menu_previous_month_utilization()

        self.assertTrue(payload)
        self.assertEqual(payload["employee_name"], self.employee.name)
        self.assertEqual(payload["period"], fields.Date.to_string(previous_period))
        self.assertAlmostEqual(payload["utilization_percentage"], 50.0, places=2)
        self.assertEqual(payload["utilization_status"], "warning")
        self.assertEqual(payload["progress_width"], 50.0)
        self.assertIn("%", payload["utilization_percentage_display"])

    def test_returns_false_when_user_has_no_linked_employee(self):
        orphan_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Bez zamestnanca",
            "login": "home_widget_orphan",
            "email": "home_widget_orphan@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.base_user_group.id, self.tenenet_user_group.id])],
        })

        payload = self.env["res.users"].with_user(orphan_user).get_home_menu_previous_month_utilization()

        self.assertFalse(payload)

    def test_returns_false_when_previous_month_utilization_is_missing(self):
        payload = self.env["res.users"].with_user(self.user).get_home_menu_previous_month_utilization()

        self.assertFalse(payload)

    def test_previous_period_rolls_back_across_year_boundary(self):
        with patch("odoo.fields.Date.context_today", return_value=date(2026, 1, 15)):
            previous_period = self._previous_period()

        self.assertEqual(previous_period, date(2025, 12, 1))
