from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetEmployeeListReport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.manager = self.env["hr.employee"].create({
            "name": "Mgr. Jana Vedúca",
        })
        self.employee = self.env["hr.employee"].create({
            "tenenet_number": 17,
            "title_academic": "Mgr.",
            "last_name": "Zamestnanec",
            "first_name": "Adam",
            "position": "Psychológ",
            "study_field": "Psychológia",
            "parent_id": self.manager.id,
            "work_ratio": 75.0,
        })
        self.report = self.env.ref("tenenet_projects.tenenet_employee_list_report")

    def _get_lines(self, search_term=None):
        options_data = {}
        if search_term:
            options_data["filter_search_bar"] = search_term
        options = self.report.get_options(options_data)
        return self.report._get_lines(options)

    def _column_map(self, line):
        return {
            column["expression_label"]: column["no_format"]
            for column in line["columns"]
        }

    def _line_for_employee(self, employee_name):
        return next(
            line for line in self._get_lines()
            if self._column_map(line)["employee_name"] == employee_name
        )

    def test_report_shows_employee_columns_from_hr_fields(self):
        line = self._line_for_employee(self.employee.name)
        columns = self._column_map(line)

        self.assertEqual(columns["employee_name"], "Mgr. Adam Zamestnanec")
        self.assertEqual(columns["tenenet_number"], "17")
        self.assertEqual(columns["title_academic"], "Mgr.")
        self.assertEqual(columns["last_name"], "Zamestnanec")
        self.assertEqual(columns["first_name"], "Adam")
        self.assertEqual(columns["position"], "Psychológ")
        self.assertEqual(columns["study_field"], "Psychológia")
        self.assertEqual(columns["manager_name"], "Mgr. Jana Vedúca")
        self.assertAlmostEqual(columns["work_hours"], 6.0, places=2)

    def test_report_search_filters_employee_rows(self):
        other_employee = self.env["hr.employee"].create({
            "title_academic": "Bc.",
            "last_name": "Kolegyňa",
            "first_name": "Beata",
        })

        lines = self._get_lines("adam")
        line_names = [self._column_map(line)["employee_name"] for line in lines]

        self.assertIn(self.employee.name, line_names)
        self.assertNotIn(other_employee.name, line_names)
