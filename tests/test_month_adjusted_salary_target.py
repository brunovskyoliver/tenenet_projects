from datetime import datetime, time

import pytz

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMonthAdjustedSalaryTarget(TransactionCase):
    def setUp(self):
        super().setUp()
        self.calendar = self.env.ref("resource.resource_calendar_std")
        self.admin_program = self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1)
        self.employee = self.env["hr.employee"].create({
            "name": "Holiday Target Employee",
            "resource_calendar_id": self.calendar.id,
            "monthly_gross_salary_target": 2300.0,
        })
        self.project = self.env["tenenet.project"].create({
            "name": "Holiday Project",
            "program_ids": [(6, 0, self.admin_program.ids)],
            "reporting_program_id": self.admin_program.id,
        })
        self.assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.project.id,
            "allocation_ratio": 50.0,
            "wage_hm": 10.0,
        })

    def _dt(self, value, hour=12, minute=0, second=0):
        tz = pytz.timezone("Europe/Bratislava")
        parsed = fields.Date.to_date(value)
        return tz.localize(datetime.combine(parsed, time(hour, minute, second))).astimezone(pytz.utc).replace(tzinfo=None)

    def _create_public_holiday(self, day, calendar_id=False, name="Veľký piatok"):
        return self.env["resource.calendar.leaves"].create({
            "name": name,
            "date_from": self._dt(day, hour=12),
            "date_to": self._dt(day, hour=23, minute=59, second=59),
            "resource_id": False,
            "calendar_id": calendar_id,
            "company_id": self.env.company.id,
            "time_type": "leave",
        })

    def test_effective_target_scales_down_for_weekday_holidays(self):
        self._create_public_holiday("2030-01-01", name="Deň vzniku Slovenskej republiky")
        self._create_public_holiday("2030-01-03", name="Zjavenie Pána")

        metrics = self.employee._get_month_workday_metrics("2030-01-01")
        effective = self.employee._get_effective_monthly_gross_salary_target("2030-01-01")

        self.assertEqual(metrics["base_workdays"], 23)
        self.assertEqual(metrics["holiday_workdays"], 2)
        self.assertEqual(metrics["effective_workdays"], 21)
        self.assertAlmostEqual(effective, 2100.0, places=2)

    def test_monthly_gross_salary_target_hm_uses_employee_contribution_multiplier(self):
        self.employee.write({
            "monthly_gross_salary_target": 1307.0,
            "tenenet_disability_type": "zps",
            "tenenet_payroll_contribution_multiplier": 1.307,
        })

        self.assertAlmostEqual(self.employee.monthly_gross_salary_target_hm, 1000.0, places=2)

        normal_employee = self.env["hr.employee"].create({
            "name": "Normal Multiplier Employee",
            "monthly_gross_salary_target": 1362.0,
        })

        self.assertAlmostEqual(normal_employee.monthly_gross_salary_target_hm, 1000.0, places=2)

    def test_disability_type_onchange_sets_disabled_and_multiplier(self):
        self.employee.tenenet_disability_type = "tzp"
        self.employee._onchange_tenenet_disability_type()

        self.assertTrue(self.employee.disabled)
        self.assertAlmostEqual(self.employee.tenenet_payroll_contribution_multiplier, 1.302, places=4)

        self.employee.disabled = False
        self.employee._onchange_tenenet_disabled()

        self.assertEqual(self.employee.tenenet_disability_type, "none")
        self.assertAlmostEqual(self.employee.tenenet_payroll_contribution_multiplier, 1.362, places=4)

    def test_weekend_holiday_does_not_reduce_target(self):
        self._create_public_holiday("2030-08-03", name="Sviatok Všetkých svätých")
        self._create_public_holiday("2030-08-29", name="Výročie Slovenského národného povstania")

        metrics = self.employee._get_month_workday_metrics("2030-08-01")

        self.assertEqual(metrics["base_workdays"], 22)
        self.assertEqual(metrics["holiday_workdays"], 1)
        self.assertEqual(metrics["effective_workdays"], 21)

    def test_fixed_ratio_and_cost_row_use_period_effective_target(self):
        self.project.write({"salary_funding_mode": "fixed_ratio"})
        self._create_public_holiday("2030-01-01", name="Deň vzniku Slovenskej republiky")
        self._create_public_holiday("2030-01-03", name="Zjavenie Pána")

        cost = self.env["tenenet.employee.tenenet.cost"]._sync_for_employee_period(
            self.employee.id,
            "2030-01-01",
        )

        self.assertAlmostEqual(self.assignment._get_fixed_salary_share("2030-01-01"), 1050.0, places=2)
        self.assertEqual(cost.base_workdays, 23)
        self.assertEqual(cost.holiday_workdays, 2)
        self.assertEqual(cost.effective_workdays, 21)
        self.assertAlmostEqual(cost.monthly_gross_salary_target, 2100.0, places=2)
        self.assertAlmostEqual(cost.fixed_ratio_covered_ccp, 1050.0, places=2)
        self.assertAlmostEqual(cost.tenenet_residual_ccp, 1050.0, places=2)

    def test_fixed_ratio_uses_period_specific_monthly_ratio(self):
        self.project.write({"salary_funding_mode": "fixed_ratio"})
        self.assignment.set_month_ratios(2030, {"1": 25.0, "2": 75.0})

        jan_target = self.employee._get_effective_monthly_gross_salary_target("2030-01-01")
        feb_target = self.employee._get_effective_monthly_gross_salary_target("2030-02-01")

        self.assertAlmostEqual(self.assignment._get_fixed_salary_share("2030-01-01"), jan_target * 0.25, places=2)
        self.assertAlmostEqual(self.assignment._get_fixed_salary_share("2030-02-01"), feb_target * 0.75, places=2)

    def test_hourly_rate_uses_effective_period_target(self):
        self._create_public_holiday("2030-01-01", name="Deň vzniku Slovenskej republiky")
        self._create_public_holiday("2030-01-03", name="Zjavenie Pána")
        self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment.id,
            "period": "2030-01-01",
            "hours_pp": 100.0,
        })

        hourly_rate = self.employee.with_context(tenenet_period="2030-01-01").hourly_rate

        self.assertAlmostEqual(hourly_rate, (2100.0 - 1362.0) / 60.0, places=2)

    def test_non_public_calendar_leave_is_ignored(self):
        self._create_public_holiday("2030-04-03", name="Veľký piatok")
        self._create_public_holiday("2030-04-08", name="Company shutdown")

        metrics = self.employee._get_month_workday_metrics("2030-04-01")

        self.assertEqual(metrics["base_workdays"], 22)
        self.assertEqual(metrics["holiday_workdays"], 1)
        self.assertEqual(metrics["effective_workdays"], 21)
