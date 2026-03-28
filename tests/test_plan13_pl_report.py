from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan13PLReport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.program_a = self.env["tenenet.program"].create({"name": "Program A", "code": "PGA"})
        self.program_b = self.env["tenenet.program"].create({"name": "Program B", "code": "PGB"})
        self.employee_a = self.env["hr.employee"].create({"name": "Adam Zamestnanec"})
        self.employee_b = self.env["hr.employee"].create({"name": "Beata Zamestnanec"})
        self.project_a = self.env["tenenet.project"].create({"name": "Projekt A", "program_ids": [(4, self.program_a.id)]})
        self.project_b = self.env["tenenet.project"].create({"name": "Projekt B", "program_ids": [(4, self.program_b.id)]})
        self.assignment_a_program_a = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_a.id,
            "project_id": self.project_a.id,
            "wage_hm": 0.0,
            "wage_ccp": 1.0,
        })
        self.assignment_b_program_a = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_b.id,
            "project_id": self.project_a.id,
            "wage_hm": 0.0,
            "wage_ccp": 1.0,
        })
        self.assignment_b_program_b = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_b.id,
            "project_id": self.project_b.id,
            "wage_hm": 0.0,
            "wage_ccp": 1.0,
        })
        self.report = self.env.ref("tenenet_projects.tenenet_pl_report")

    def _pl(self, assignment, period, amount):
        self.env["tenenet.project.timesheet"].create({
            "assignment_id": assignment.id,
            "period": period,
            "hours_pp": amount,
        })
        return self.env["tenenet.pl.line"].create({
            "employee_id": assignment.employee_id.id,
            "program_id": assignment.project_id.program_ids[:1].id,
            "period": period,
        })

    def _get_lines(self, date_to, unfolded_lines=None):
        options_data = {
            "date": {
                "mode": "single",
                "filter": "custom",
                "date_to": date_to,
            },
        }
        if unfolded_lines:
            options_data["unfolded_lines"] = unfolded_lines
        options = self.report.get_options(options_data)
        return self.report._get_lines(options)

    def _column_map(self, line):
        return {
            column["expression_label"]: column["no_format"]
            for column in line["columns"]
        }

    def test_report_groups_by_program_and_shows_negative_monthly_profit_loss(self):
        self._pl(self.assignment_a_program_a, "2026-01-01", 100.0)
        self._pl(self.assignment_b_program_a, "2026-02-01", 50.0)
        self._pl(self.assignment_b_program_b, "2026-01-01", 80.0)

        lines = self._get_lines("2026-12-31")
        program_a_line = next(line for line in lines if line["name"] == "Program A")
        program_b_line = next(line for line in lines if line["name"] == "Program B")
        total_line = next(line for line in lines if line["name"] == "Zisk / strata spolu")

        program_a_columns = self._column_map(program_a_line)
        program_b_columns = self._column_map(program_b_line)
        total_columns = self._column_map(total_line)

        self.assertAlmostEqual(program_a_columns["month_01"], -100.0, places=2)
        self.assertAlmostEqual(program_a_columns["month_02"], -50.0, places=2)
        self.assertAlmostEqual(program_a_columns["year_total"], -150.0, places=2)
        self.assertAlmostEqual(program_b_columns["month_01"], -80.0, places=2)
        self.assertAlmostEqual(program_b_columns["year_total"], -80.0, places=2)
        self.assertAlmostEqual(total_columns["month_01"], -180.0, places=2)
        self.assertAlmostEqual(total_columns["month_02"], -50.0, places=2)
        self.assertAlmostEqual(total_columns["year_total"], -230.0, places=2)

    def test_unfolding_program_shows_category_detail(self):
        self._pl(self.assignment_a_program_a, "2026-01-01", 100.0)
        self._pl(self.assignment_a_program_a, "2026-03-01", 40.0)
        self._pl(self.assignment_b_program_a, "2026-01-01", 75.0)

        program_line_id = self.report._get_generic_line_id(
            "tenenet.program",
            self.program_a.id,
            markup="tenenet_pl_program",
        )
        lines = self._get_lines("2026-12-31", unfolded_lines=[program_line_id])

        detail_lines = [
            line for line in lines
            if line.get("parent_id") == program_line_id and not line["name"].startswith("Total ")
        ]
        self.assertEqual([line["name"] for line in detail_lines], [
            "Projekt A",
            "Príjmy/výnosy",
            "Príjmy spolu",
            "Náklady",
            "Mzdové náklady - program",
            "Stravné a iné",
            "Zisk/strata - vykrytie mzdových nákladov",
            "Admin a manažérske náklady",
            "Mzdové náklady - podporné odd./admin",
            "Mzdové náklady - manažment",
            "Prevádzkové náklady",
            "Zisk/strata - za program",
        ])

        labor_cost_columns = self._column_map(next(line for line in detail_lines if line["name"] == "Mzdové náklady - program"))
        profit_loss_columns = self._column_map(next(line for line in detail_lines if line["name"] == "Zisk/strata - za program"))
        placeholder_columns = self._column_map(next(line for line in detail_lines if line["name"] == "Stravné a iné"))

        self.assertAlmostEqual(labor_cost_columns["month_01"], -175.0, places=2)
        self.assertAlmostEqual(labor_cost_columns["month_03"], -40.0, places=2)
        self.assertAlmostEqual(labor_cost_columns["year_total"], -215.0, places=2)
        self.assertAlmostEqual(placeholder_columns["month_01"], 0.0, places=2)
        self.assertAlmostEqual(placeholder_columns["year_total"], 0.0, places=2)
        self.assertAlmostEqual(profit_loss_columns["month_01"], -175.0, places=2)
        self.assertAlmostEqual(profit_loss_columns["month_03"], -40.0, places=2)
        self.assertAlmostEqual(profit_loss_columns["year_total"], -215.0, places=2)

    def test_single_line_expand_function_returns_program_detail(self):
        self._pl(self.assignment_a_program_a, "2026-01-01", 100.0)
        options = self.report.get_options({
            "date": {
                "mode": "single",
                "filter": "custom",
                "date_to": "2026-12-31",
            },
        })
        top_lines = self.report._get_lines(options)
        program_line = next(line for line in top_lines if line["name"] == "Program A")

        expanded_lines = self.report.get_expanded_lines(
            options,
            program_line["id"],
            program_line.get("groupby"),
            program_line["expand_function"],
            program_line.get("progress"),
            0,
            program_line.get("horizontal_split_side"),
        )

        self.assertEqual(
            [line["name"] for line in expanded_lines if not line["name"].startswith("Total ")],
            [
                "Projekt A",
                "Príjmy/výnosy",
                "Príjmy spolu",
                "Náklady",
                "Mzdové náklady - program",
                "Stravné a iné",
                "Zisk/strata - vykrytie mzdových nákladov",
                "Admin a manažérske náklady",
                "Mzdové náklady - podporné odd./admin",
                "Mzdové náklady - manažment",
                "Prevádzkové náklady",
                "Zisk/strata - za program",
            ],
        )
        self.assertTrue(all(line["id"].startswith(f"{program_line['id']}|") for line in expanded_lines))

    def test_unfolding_program_lists_project_rows_without_workbook_sections(self):
        project_international = self.env["tenenet.project"].create({
            "name": "International Alpha",
            "code": "INT-ALPHA",
            "program_id": self.program_a.id,
        })
        project_national = self.env["tenenet.project"].create({
            "name": "National Beta",
            "code": "NAT-BETA",
            "program_id": self.program_a.id,
        })
        assignment_international = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_a.id,
            "project_id": project_international.id,
            "wage_hm": 0.0,
            "wage_ccp": 1.0,
        })
        assignment_national = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_b.id,
            "project_id": project_national.id,
            "wage_hm": 0.0,
            "wage_ccp": 1.0,
        })
        self._pl(assignment_international, "2026-01-01", 100.0)
        self._pl(assignment_national, "2026-02-01", 50.0)

        program_line_id = self.report._get_generic_line_id(
            "tenenet.program",
            self.program_a.id,
            markup="tenenet_pl_program",
        )
        lines = self._get_lines("2026-12-31", unfolded_lines=[program_line_id])

        expanded_names = [line["name"] for line in lines if line["id"].startswith(f"{program_line_id}|")]
        self.assertEqual(expanded_names[:2], [
            "INT-ALPHA International Alpha",
            "NAT-BETA National Beta",
        ])

    def test_year_filter_limits_data_to_selected_year(self):
        self._pl(self.assignment_a_program_a, "2025-12-01", 25.0)
        self._pl(self.assignment_a_program_a, "2026-01-01", 100.0)

        lines_2025 = self._get_lines("2025-12-31")
        lines_2026 = self._get_lines("2026-12-31")

        columns_2025 = self._column_map(next(line for line in lines_2025 if line["name"] == "Program A"))
        columns_2026 = self._column_map(next(line for line in lines_2026 if line["name"] == "Program A"))

        self.assertAlmostEqual(columns_2025["month_12"], -25.0, places=2)
        self.assertAlmostEqual(columns_2025["year_total"], -25.0, places=2)
        self.assertAlmostEqual(columns_2026["month_01"], -100.0, places=2)
        self.assertAlmostEqual(columns_2026["year_total"], -100.0, places=2)

    def test_program_without_pl_lines_is_still_listed(self):
        program_c = self.env["tenenet.program"].create({"name": "Program C", "code": "PGC"})

        lines = self._get_lines("2026-12-31")
        program_c_line = next(line for line in lines if line["name"] == program_c.name)
        program_c_columns = self._column_map(program_c_line)

        self.assertAlmostEqual(program_c_columns["month_01"], 0.0, places=2)
        self.assertAlmostEqual(program_c_columns["year_total"], 0.0, places=2)

    def test_report_uses_timesheet_costs_when_pl_lines_are_missing(self):
        self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment_b_program_b.id,
            "period": "2026-04-01",
            "hours_pp": 20.0,
        })

        lines = self._get_lines("2026-12-31")
        program_b_line = next(line for line in lines if line["name"] == "Program B")
        program_b_columns = self._column_map(program_b_line)

        self.assertAlmostEqual(program_b_columns["month_04"], -20.0, places=2)
        self.assertAlmostEqual(program_b_columns["year_total"], -20.0, places=2)

    def test_opening_report_syncs_pl_lines_for_selected_year(self):
        self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment_b_program_b.id,
            "period": "2026-05-01",
            "hours_pp": 30.0,
        })

        self.assertFalse(
            self.env["tenenet.pl.line"].search([
                ("employee_id", "=", self.assignment_b_program_b.employee_id.id),
                ("program_id", "=", self.assignment_b_program_b.project_id.program_ids[:1].id),
                ("period", "=", "2026-05-01"),
            ])
        )

        self._get_lines("2026-12-31")

        synced_line = self.env["tenenet.pl.line"].search([
            ("employee_id", "=", self.assignment_b_program_b.employee_id.id),
            ("program_id", "=", self.assignment_b_program_b.project_id.program_ids[:1].id),
            ("period", "=", "2026-05-01"),
        ])
        self.assertTrue(synced_line)
        self.assertAlmostEqual(synced_line.amount, 30.0, places=2)

    def test_report_ignores_workbook_and_uses_odoo_values_for_matching_program_year(self):
        workbook_program = self.env["tenenet.program"].search([("code", "=", "VCI")], limit=1)
        self.assertTrue(workbook_program)
        employee = self.env["hr.employee"].create({"name": "VCI Employee"})
        project = self.env["tenenet.project"].create({
            "name": "VCI Project",
            "program_id": workbook_program.id,
        })
        assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": employee.id,
            "project_id": project.id,
            "wage_hm": 0.0,
            "wage_ccp": 1.0,
        })

        self._pl(assignment, "2025-01-01", 111.0)

        lines = self._get_lines("2025-12-31")
        workbook_line = next(line for line in lines if line["name"] == workbook_program.name)
        workbook_columns = self._column_map(workbook_line)

        self.assertAlmostEqual(workbook_columns["month_01"], -111.0, places=2)
        self.assertAlmostEqual(workbook_columns["month_02"], 0.0, places=2)
        self.assertAlmostEqual(workbook_columns["year_total"], -111.0, places=2)
