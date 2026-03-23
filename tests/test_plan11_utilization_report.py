from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan11UtilizationReport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.manager_a = self.env["hr.employee"].create({"name": "Manager A"})
        self.manager_b = self.env["hr.employee"].create({"name": "Manager B"})
        self.calendar_8h = self.env["resource.calendar"].create({"name": "Kalendár report 8h"})
        self.calendar_8h.hours_per_day = 8.0

        self.employee_a = self.env["hr.employee"].create(
            {
                "name": "Adam Zamestnanec",
                "parent_id": self.manager_a.id,
                "resource_calendar_id": self.calendar_8h.id,
            }
        )
        self.employee_b = self.env["hr.employee"].create(
            {
                "name": "Beata Zamestnanec",
                "parent_id": self.manager_b.id,
                "resource_calendar_id": self.calendar_8h.id,
            }
        )
        self.project = self.env["tenenet.project"].create({"name": "Projekt report"})
        self.assignment_a = self.env["tenenet.project.assignment"].create(
            {
                "employee_id": self.employee_a.id,
                "project_id": self.project.id,
                "wage_hm": 10.0,
                "wage_ccp": 13.62,
            }
        )
        self.assignment_b = self.env["tenenet.project.assignment"].create(
            {
                "employee_id": self.employee_b.id,
                "project_id": self.project.id,
                "wage_hm": 10.0,
                "wage_ccp": 13.62,
            }
        )
        self.report = self.env.ref("tenenet_projects.tenenet_utilization_report")

        base_user_group = self.env.ref("base.group_user")
        tenenet_user_group = self.env.ref("tenenet_projects.group_tenenet_user")
        self.user_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Používateľ reportu",
                "login": "utilization_report_user",
                "email": "utilization_report_user@example.com",
                "company_id": self.env.company.id,
                "company_ids": [Command.set([self.env.company.id])],
                "group_ids": [Command.set([base_user_group.id, tenenet_user_group.id])],
            }
        )

    def _create_timesheet(self, assignment, period, **hours):
        vals = {"assignment_id": assignment.id, "period": period}
        vals.update(hours)
        return self.env["tenenet.project.timesheet"].with_context(from_hr_leave_sync=True).create(vals)

    def _get_lines(self, date_to, user=None):
        report = self.report.with_user(user) if user else self.report
        options = report.get_options(
            {
                "date": {
                    "mode": "single",
                    "filter": "custom",
                    "date_to": date_to,
                }
            }
        )
        return report._get_lines(options), options

    def _find_employee_line(self, lines, employee_name):
        return next(line for line in lines if line["name"] == employee_name)

    def _line_names(self, lines):
        return [line["name"] for line in lines]

    def _column_map(self, line):
        return {
            column["expression_label"]: column["no_format"]
            for column in line["columns"]
        }

    def test_report_syncs_all_active_employees_for_selected_month(self):
        lines, _options = self._get_lines("2026-02-18")

        line_names = self._line_names(lines)
        self.assertIn("Adam Zamestnanec", line_names)
        self.assertIn("Beata Zamestnanec", line_names)

        records = self.env["tenenet.utilization"].search([("period", "=", "2026-02-01")])
        self.assertIn(self.employee_a, records.mapped("employee_id"))
        self.assertIn(self.employee_b, records.mapped("employee_id"))

    def test_report_uses_normalized_month_and_matches_utilization_values(self):
        self._create_timesheet(
            self.assignment_a,
            "2026-03-01",
            hours_pp=90.0,
            hours_np=12.0,
            hours_travel=4.0,
            hours_training=3.0,
            hours_ambulance=2.0,
            hours_international=1.0,
            hours_vacation=8.0,
            hours_doctor=2.0,
            hours_sick=1.0,
            hours_holidays=5.0,
        )

        lines, _options = self._get_lines("2026-03-18")
        adam_line = self._find_employee_line(lines, "Adam Zamestnanec")
        columns = self._column_map(adam_line)
        utilization = self.env["tenenet.utilization"].search(
            [("employee_id", "=", self.employee_a.id), ("period", "=", "2026-03-01")],
            limit=1,
        )

        self.assertTrue(utilization)
        self.assertEqual(columns["manager_name"], "Manager A")
        self.assertAlmostEqual(columns["hours_pp"], utilization.hours_pp, places=2)
        self.assertAlmostEqual(columns["hours_np"], utilization.hours_np, places=2)
        self.assertAlmostEqual(columns["hours_project_total"], utilization.hours_project_total, places=2)
        self.assertAlmostEqual(columns["hours_ballast"], utilization.hours_ballast, places=2)
        self.assertAlmostEqual(columns["utilization_percentage"], utilization.utilization_rate * 100.0, places=2)
        self.assertEqual(columns["utilization_status"], utilization.utilization_status)
        self.assertAlmostEqual(columns["non_project_percentage"], utilization.non_project_rate * 100.0, places=2)
        self.assertEqual(columns["non_project_status"], utilization.non_project_status)

    def test_report_month_switch_changes_dataset(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", hours_pp=10.0)
        self._create_timesheet(self.assignment_a, "2026-02-01", hours_pp=20.0)

        january_lines, _january_options = self._get_lines("2026-01-15")
        february_lines, _february_options = self._get_lines("2026-02-15")

        january_columns = self._column_map(self._find_employee_line(january_lines, "Adam Zamestnanec"))
        february_columns = self._column_map(self._find_employee_line(february_lines, "Adam Zamestnanec"))

        self.assertAlmostEqual(january_columns["hours_pp"], 10.0, places=2)
        self.assertAlmostEqual(february_columns["hours_pp"], 20.0, places=2)

    def test_report_sorts_by_manager_then_employee(self):
        self.employee_a.parent_id = self.manager_b
        self.employee_b.parent_id = self.manager_a

        lines, _options = self._get_lines("2026-04-01")
        line_names = self._line_names(lines)

        self.assertLess(line_names.index("Beata Zamestnanec"), line_names.index("Adam Zamestnanec"))

    def test_readonly_tenenet_user_can_open_report(self):
        lines, _options = self._get_lines("2026-05-10", user=self.user_user)

        line_names = self._line_names(lines)
        self.assertIn("Adam Zamestnanec", line_names)
        self.assertIn("Beata Zamestnanec", line_names)
