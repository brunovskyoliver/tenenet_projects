from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan11UtilizationReport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.manager_a = self.env["hr.employee"].create({"name": "Manager A"})
        self.manager_b = self.env["hr.employee"].create({"name": "Manager B"})
        self.employee_a = self.env["hr.employee"].create(
            {
                "name": "Adam Zamestnanec",
                "parent_id": self.manager_a.id,
                "work_ratio": 100.0,
            }
        )
        self.employee_b = self.env["hr.employee"].create(
            {
                "name": "Beata Zamestnanec",
                "parent_id": self.manager_b.id,
                "work_ratio": 100.0,
            }
        )
        self.donor_national = self.env["tenenet.donor"].create({
            "name": "Národný donor",
            "donor_type": "sr_ministerstvo",
        })
        self.donor_international = self.env["tenenet.donor"].create({
            "name": "Medzinárodný donor",
            "donor_type": "international",
        })
        self.project = self.env["tenenet.project"].create({
            "name": "Národný projekt",
            "donor_id": self.donor_national.id,
        })
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
        timesheet = self.env["tenenet.project.timesheet"]._get_or_create_for_assignment_period(assignment, period)
        if hours:
            timesheet.with_context(from_hr_leave_sync=True).write(hours)
        return timesheet

    def _get_lines(self, date_to, user=None, unfolded_lines=None):
        report = self.report.with_user(user) if user else self.report
        options_data = {
            "date": {
                "mode": "single",
                "filter": "custom",
                "date_to": date_to,
            }
        }
        if unfolded_lines:
            options_data["unfolded_lines"] = unfolded_lines
        options = report.get_options(options_data)
        return report._get_lines(options), options

    def _find_employee_line(self, lines, employee_name):
        return next(line for line in lines if line["name"] == employee_name)

    def _find_line(self, lines, line_name):
        return next(line for line in lines if line["name"] == line_name)

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
        self.assertEqual(columns["project_type"], "N: 1 / M: 0")
        self.assertAlmostEqual(columns["monthly_project_income"], 0.0, places=2)
        self.assertAlmostEqual(columns["project_insurance_income"], 0.0, places=2)

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

    def test_employee_unfold_shows_projects_with_aggregated_assignments(self):
        self.assignment_a.write({
            "allocation_ratio": 50.0,
            "date_start": "2026-01-01",
        })
        international_project = self.env["tenenet.project"].create({
            "name": "Medzinárodný projekt",
            "donor_id": self.donor_national.id,
            "international": True,
        })
        assignment_int_a = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_a.id,
            "project_id": international_project.id,
            "allocation_ratio": 40.0,
            "date_start": "2026-01-01",
            "wage_hm": 11.0,
            "wage_ccp": 14.98,
        })
        assignment_int_b = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_a.id,
            "project_id": international_project.id,
            "allocation_ratio": 10.0,
            "date_start": "2026-02-01",
            "wage_hm": 12.0,
            "wage_ccp": 16.34,
        })

        self._create_timesheet(self.assignment_a, "2026-03-01", hours_pp=30.0, hours_np=5.0)
        self._create_timesheet(assignment_int_a, "2026-03-01", hours_pp=20.0, hours_travel=2.0)
        self._create_timesheet(assignment_int_b, "2026-03-01", hours_pp=10.0, hours_training=1.0)

        top_lines, options = self._get_lines("2026-03-18")
        adam_line = self._find_employee_line(top_lines, "Adam Zamestnanec")
        adam_columns = self._column_map(adam_line)

        self.assertTrue(adam_line["unfoldable"])
        self.assertEqual(adam_columns["project_type"], "N: 1 / M: 2")
        self.assertAlmostEqual(adam_columns["monthly_project_income"], 0.0, places=2)
        self.assertAlmostEqual(adam_columns["project_insurance_income"], 0.0, places=2)

        project_lines = self.report.get_expanded_lines(
            options,
            adam_line["id"],
            adam_line.get("groupby"),
            adam_line["expand_function"],
            adam_line.get("progress"),
            0,
            adam_line.get("horizontal_split_side"),
        )
        self.assertEqual(
            [line["name"] for line in project_lines if not line["name"].startswith("Total ")],
            ["Medzinárodný projekt", "Národný projekt"],
        )

        international_line = self._find_line(project_lines, "Medzinárodný projekt")
        international_columns = self._column_map(international_line)
        self.assertEqual(international_columns["project_type"], "Medzinárodný")
        self.assertAlmostEqual(international_columns["work_ratio"], 50.0, places=2)
        self.assertAlmostEqual(international_columns["capacity_hours"], 80.0, places=2)
        self.assertAlmostEqual(international_columns["hours_pp"], 30.0, places=2)
        self.assertAlmostEqual(international_columns["monthly_project_income"], 0.0, places=2)
        self.assertAlmostEqual(international_columns["project_insurance_income"], 0.0, places=2)
        self.assertFalse(international_line.get("unfoldable"))
        self.assertFalse(international_line.get("expand_function"))

    def test_unfolded_lines_option_returns_project_rows_only(self):
        self.employee_a.work_ratio = 130.0
        international_project = self.env["tenenet.project"].create({
            "name": "Medzinárodný projekt 2",
            "donor_id": self.donor_national.id,
            "international": True,
        })
        assignment_int = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_a.id,
            "project_id": international_project.id,
            "allocation_ratio": 30.0,
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        })
        self._create_timesheet(assignment_int, "2026-06-01", hours_pp=15.0)

        top_lines, _options = self._get_lines("2026-06-10")
        adam_line = self._find_employee_line(top_lines, "Adam Zamestnanec")
        employee_line_id = adam_line["id"]

        unfolded_lines, _options = self._get_lines(
            "2026-06-10",
            unfolded_lines=[employee_line_id],
        )
        unfolded_names = [line["name"] for line in unfolded_lines]
        self.assertIn("Medzinárodný projekt 2", unfolded_names)
        self.assertNotIn("Úväzok 30 %", unfolded_names)
        self.assertFalse(any(name.startswith("Total ") for name in unfolded_names))

    def test_employee_with_assignment_but_without_timesheet_is_still_unfoldable(self):
        support_project = self.env["tenenet.project"].create({
            "name": "Podporný projekt",
            "donor_id": self.donor_national.id,
        })
        self.assignment_b.unlink()
        assignment_support = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_b.id,
            "project_id": support_project.id,
            "allocation_ratio": 100.0,
            "date_start": "2026-06-01",
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        })

        top_lines, options = self._get_lines("2026-06-10")
        beata_line = self._find_employee_line(top_lines, "Beata Zamestnanec")
        beata_columns = self._column_map(beata_line)

        self.assertTrue(beata_line["unfoldable"])
        self.assertEqual(beata_columns["project_type"], "N: 1 / M: 0")

        project_lines = self.report.get_expanded_lines(
            options,
            beata_line["id"],
            beata_line.get("groupby"),
            beata_line["expand_function"],
            beata_line.get("progress"),
            0,
            beata_line.get("horizontal_split_side"),
        )
        self.assertEqual(
            [line["name"] for line in project_lines if not line["name"].startswith("Total ")],
            ["Podporný projekt"],
        )

        project_line = self._find_line(project_lines, "Podporný projekt")
        project_columns = self._column_map(project_line)
        self.assertFalse(project_line.get("unfoldable"))
        self.assertEqual(project_columns["project_type"], "Národný")
        self.assertAlmostEqual(project_columns["work_ratio"], 100.0, places=2)
        self.assertAlmostEqual(project_columns["capacity_hours"], 160.0, places=2)
        self.assertAlmostEqual(project_columns["hours_pp"], 0.0, places=2)
        self.assertEqual(assignment_support.employee_id, self.employee_b)

    def test_project_checkbox_overrides_donor_classification_in_report(self):
        self.employee_a.work_ratio = 120.0
        project = self.env["tenenet.project"].create({
            "name": "Lokálny podľa checkboxu",
            "donor_id": self.donor_international.id,
            "international": False,
        })
        assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_a.id,
            "project_id": project.id,
            "allocation_ratio": 20.0,
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        })
        self._create_timesheet(assignment, "2026-08-01", hours_pp=10.0)

        top_lines, options = self._get_lines("2026-08-18")
        adam_line = self._find_employee_line(top_lines, "Adam Zamestnanec")
        self.assertEqual(self._column_map(adam_line)["project_type"], "N: 2 / M: 0")

        project_lines = self.report.get_expanded_lines(
            options,
            adam_line["id"],
            adam_line.get("groupby"),
            adam_line["expand_function"],
            adam_line.get("progress"),
            0,
            adam_line.get("horizontal_split_side"),
        )
        project_line = self._find_line(project_lines, "Lokálny podľa checkboxu")
        self.assertEqual(self._column_map(project_line)["project_type"], "Národný")

    def test_report_hides_total_rows(self):
        top_lines, options = self._get_lines("2026-03-18")

        self.assertFalse(any(line["name"].startswith("Total ") for line in top_lines))

        adam_line = self._find_employee_line(top_lines, "Adam Zamestnanec")
        project_lines = self.report.get_expanded_lines(
            options,
            adam_line["id"],
            adam_line.get("groupby"),
            adam_line["expand_function"],
            adam_line.get("progress"),
            0,
            adam_line.get("horizontal_split_side"),
        )
        self.assertFalse(any(line["name"].startswith("Total ") for line in project_lines))
