from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetInternalExpenseReport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.report_year = 2100
        self.employee_a = self.env["hr.employee"].create({"name": "Adam Interny"})
        self.employee_b = self.env["hr.employee"].create({"name": "Beata Interna"})
        self.project_a = self.env["tenenet.project"].create({"name": "Projekt Alfa"})
        self.project_b = self.env["tenenet.project"].create({"name": "Projekt Beta"})
        self.type_phone = self.env["tenenet.expense.type.config"].create({"name": "Telefón"})
        self.type_rent = self.env["tenenet.expense.type.config"].create({"name": "Nájom"})

        self.employee_report = self.env.ref("tenenet_projects.tenenet_internal_expense_report")
        self.project_report = self.env.ref("tenenet_projects.tenenet_internal_expense_project_report")

        self.env["tenenet.internal.expense"].create([
            {
                "employee_id": self.employee_a.id,
                "period": f"{self.report_year}-01-01",
                "category": "expense",
                "source_project_id": self.project_a.id,
                "expense_type_config_id": self.type_phone.id,
                "expense_amount": 100.0,
            },
            {
                "employee_id": self.employee_a.id,
                "period": f"{self.report_year}-02-01",
                "category": "expense",
                "source_project_id": self.project_b.id,
                "expense_type_config_id": self.type_rent.id,
                "expense_amount": 50.0,
            },
            {
                "employee_id": self.employee_b.id,
                "period": f"{self.report_year}-03-01",
                "category": "expense",
                "source_project_id": self.project_a.id,
                "expense_type_config_id": self.type_rent.id,
                "expense_amount": 75.0,
            },
        ])

    def _get_lines(self, report, date_to=None, unfolded_lines=None):
        if date_to is None:
            date_to = f"{self.report_year}-12-31"
        options_data = {
            "date": {
                "mode": "single",
                "filter": "custom",
                "date_to": date_to,
            },
        }
        if unfolded_lines:
            options_data["unfolded_lines"] = unfolded_lines
        options = report.get_options(options_data)
        return report._get_lines(options), options

    def _find_line(self, lines, name, parent_id=None):
        return next(
            line for line in lines
            if line["name"] == name and (parent_id is None or line.get("parent_id") == parent_id)
        )

    def _column_map(self, line, options):
        return {
            (column.get("expression_label") or options["columns"][index]["expression_label"]): column["no_format"]
            for index, column in enumerate(line["columns"])
        }

    def test_employee_report_keeps_employee_first_hierarchy(self):
        lines, options = self._get_lines(self.employee_report)
        line_names = [line["name"] for line in lines]
        self.assertIn("Adam Interny", line_names)
        self.assertIn("Beata Interna", line_names)
        self.assertIn("Náklady interných výdavkov spolu (€)", line_names)

        employee_line = self._find_line(lines, "Adam Interny")
        expanded = self.employee_report.get_expanded_lines(
            options,
            employee_line["id"],
            employee_line.get("groupby"),
            employee_line["expand_function"],
            employee_line.get("progress"),
            0,
            employee_line.get("horizontal_split_side"),
        )
        expanded_names = [line["name"] for line in expanded if not line["name"].startswith("Total ")]
        self.assertEqual(expanded_names, ["Projekt Alfa", "Projekt Beta"])

        project_line = self._find_line(expanded, "Projekt Alfa")
        detail_lines = self.employee_report.get_expanded_lines(
            options,
            project_line["id"],
            project_line.get("groupby"),
            project_line["expand_function"],
            project_line.get("progress"),
            0,
            project_line.get("horizontal_split_side"),
        )
        self.assertEqual([line["name"] for line in detail_lines], ["Náklady - Telefón"])

    def test_project_report_groups_by_project_and_matches_totals(self):
        lines, options = self._get_lines(self.project_report)
        line_names = [line["name"] for line in lines]
        self.assertIn("Projekt Alfa", line_names)
        self.assertIn("Projekt Beta", line_names)
        self.assertIn("Náklady interných výdavkov spolu (€)", line_names)

        project_line = self._find_line(lines, "Projekt Alfa")
        project_columns = self._column_map(project_line, options)
        total_columns = self._column_map(self._find_line(lines, "Náklady interných výdavkov spolu (€)"), options)

        self.assertAlmostEqual(project_columns["month_01"], 100.0, places=2)
        self.assertAlmostEqual(project_columns["month_03"], 75.0, places=2)
        self.assertAlmostEqual(project_columns["year_total"], 175.0, places=2)
        self.assertAlmostEqual(total_columns["year_total"], 225.0, places=2)

        expanded = self.project_report.get_expanded_lines(
            options,
            project_line["id"],
            project_line.get("groupby"),
            project_line["expand_function"],
            project_line.get("progress"),
            0,
            project_line.get("horizontal_split_side"),
        )
        expanded_names = [line["name"] for line in expanded if not line["name"].startswith("Total ")]
        self.assertEqual(expanded_names, ["Adam Interny", "Beata Interna"])

        employee_line = self._find_line(expanded, "Beata Interna", parent_id=project_line["id"])
        detail_lines = self.project_report.get_expanded_lines(
            options,
            employee_line["id"],
            employee_line.get("groupby"),
            employee_line["expand_function"],
            employee_line.get("progress"),
            0,
            employee_line.get("horizontal_split_side"),
        )
        self.assertEqual([line["name"] for line in detail_lines], ["Náklady - Nájom"])
