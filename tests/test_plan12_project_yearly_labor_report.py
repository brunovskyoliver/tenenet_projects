from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan12ProjectYearlyLaborReport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee_a = self.env["hr.employee"].create({"name": "Adam Zamestnanec"})
        self.employee_b = self.env["hr.employee"].create({"name": "Beata Zamestnanec"})

        self.project_a = self.env["tenenet.project"].create({"name": "Projekt A"})
        self.project_b = self.env["tenenet.project"].create({"name": "Projekt B"})

        self.assignment_a = self.env["tenenet.project.assignment"].create(
            {
                "employee_id": self.employee_a.id,
                "project_id": self.project_a.id,
                "wage_hm": 10.0,
                "wage_ccp": 20.0,
            }
        )
        self.assignment_b = self.env["tenenet.project.assignment"].create(
            {
                "employee_id": self.employee_b.id,
                "project_id": self.project_a.id,
                "wage_hm": 12.0,
                "wage_ccp": 30.0,
            }
        )
        self.assignment_other_project = self.env["tenenet.project.assignment"].create(
            {
                "employee_id": self.employee_a.id,
                "project_id": self.project_b.id,
                "wage_hm": 10.0,
                "wage_ccp": 20.0,
            }
        )
        self.report = self.env.ref("tenenet_projects.tenenet_project_yearly_labor_report")

    def _create_timesheet(self, assignment, period, hours_total):
        return self.env["tenenet.project.timesheet"].create(
            {
                "assignment_id": assignment.id,
                "period": period,
                "hours_pp": hours_total,
            }
        )

    def _get_lines(self, project, date_to):
        options = self.report.get_options(
            {
                "project_ids": [project.id],
                "date": {
                    "mode": "single",
                    "filter": "custom",
                    "date_to": date_to,
                },
            }
        )
        return self.report._get_lines(options)

    def _find_line(self, lines, line_id):
        return next(line for line in lines if line["id"] == line_id)

    def _find_employee_metric_line(self, lines, employee, metric_label):
        return next(
            line
            for line in lines
            if line["name"] == employee.name and self._column_map(line)["metric_label"] == metric_label
        )

    def _find_total_line(self, lines, line_name):
        return next(line for line in lines if line["name"] == line_name)

    def _column_map(self, line):
        return {
            column["expression_label"]: column["no_format"]
            for column in line["columns"]
        }

    def test_report_returns_two_rows_per_employee_and_total_rows(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", 10.0)
        self._create_timesheet(self.assignment_b, "2026-02-01", 15.0)

        lines = self._get_lines(self.project_a, "2026-12-31")
        self.assertEqual([line["name"] for line in lines], [
            "Adam Zamestnanec",
            "Adam Zamestnanec",
            "Beata Zamestnanec",
            "Beata Zamestnanec",
            "Hodiny spolu",
            "Suma spolu",
        ])

        self.assertEqual(self._column_map(lines[0])["metric_label"], "Celková cena práce")
        self.assertEqual(self._column_map(lines[1])["metric_label"], "Odpracované hodiny")
        self.assertEqual(self._column_map(lines[2])["metric_label"], "Celková cena práce")
        self.assertEqual(self._column_map(lines[3])["metric_label"], "Odpracované hodiny")

    def test_report_month_values_and_year_total_match_timesheets(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", 10.0)
        self._create_timesheet(self.assignment_a, "2026-03-01", 12.5)

        lines = self._get_lines(self.project_a, "2026-12-31")
        amount_line = self._find_employee_metric_line(lines, self.employee_a, "Celková cena práce")
        hours_line = self._find_employee_metric_line(lines, self.employee_a, "Odpracované hodiny")

        amount_columns = self._column_map(amount_line)
        hours_columns = self._column_map(hours_line)

        self.assertEqual(amount_columns["metric_label"], "Celková cena práce")
        self.assertEqual(hours_columns["metric_label"], "Odpracované hodiny")
        self.assertAlmostEqual(amount_columns["month_01"], 200.0, places=2)
        self.assertAlmostEqual(amount_columns["month_03"], 250.0, places=2)
        self.assertAlmostEqual(amount_columns["year_total"], 450.0, places=2)
        self.assertAlmostEqual(hours_columns["month_01"], 10.0, places=2)
        self.assertAlmostEqual(hours_columns["month_03"], 12.5, places=2)
        self.assertAlmostEqual(hours_columns["year_total"], 22.5, places=2)

    def test_report_totals_sum_all_employee_rows(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", 10.0)
        self._create_timesheet(self.assignment_b, "2026-01-01", 15.0)
        self._create_timesheet(self.assignment_b, "2026-02-01", 5.0)

        lines = self._get_lines(self.project_a, "2026-12-31")
        total_hours_line = self._find_total_line(lines, "Hodiny spolu")
        total_amount_line = self._find_total_line(lines, "Suma spolu")

        total_hours_columns = self._column_map(total_hours_line)
        total_amount_columns = self._column_map(total_amount_line)

        self.assertAlmostEqual(total_hours_columns["month_01"], 25.0, places=2)
        self.assertAlmostEqual(total_hours_columns["month_02"], 5.0, places=2)
        self.assertAlmostEqual(total_hours_columns["year_total"], 30.0, places=2)
        self.assertAlmostEqual(total_amount_columns["month_01"], 650.0, places=2)
        self.assertAlmostEqual(total_amount_columns["month_02"], 150.0, places=2)
        self.assertAlmostEqual(total_amount_columns["year_total"], 800.0, places=2)

    def test_project_and_year_filters_change_dataset(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", 10.0)
        self._create_timesheet(self.assignment_a, "2027-01-01", 20.0)
        self._create_timesheet(self.assignment_other_project, "2026-01-01", 30.0)

        project_a_2026 = self._get_lines(self.project_a, "2026-12-31")
        project_a_2027 = self._get_lines(self.project_a, "2027-12-31")
        project_b_2026 = self._get_lines(self.project_b, "2026-12-31")

        project_a_2026_hours = self._column_map(
            self._find_employee_metric_line(project_a_2026, self.employee_a, "Odpracované hodiny")
        )
        project_a_2027_hours = self._column_map(
            self._find_employee_metric_line(project_a_2027, self.employee_a, "Odpracované hodiny")
        )
        project_b_2026_hours = self._column_map(
            self._find_employee_metric_line(project_b_2026, self.employee_a, "Odpracované hodiny")
        )

        self.assertAlmostEqual(project_a_2026_hours["year_total"], 10.0, places=2)
        self.assertAlmostEqual(project_a_2027_hours["year_total"], 20.0, places=2)
        self.assertAlmostEqual(project_b_2026_hours["year_total"], 30.0, places=2)

    def test_only_employees_with_data_are_listed(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", 10.0)

        lines = self._get_lines(self.project_a, "2026-12-31")
        employee_rows = [
            (line["name"], self._column_map(line)["metric_label"])
            for line in lines
            if line["name"] not in {"Hodiny spolu", "Suma spolu"}
        ]

        self.assertIn(("Adam Zamestnanec", "Odpracované hodiny"), employee_rows)
        self.assertNotIn(("Beata Zamestnanec", "Odpracované hodiny"), employee_rows)
