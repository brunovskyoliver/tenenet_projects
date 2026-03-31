from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan13PLReport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.base_wage_hm = 1.0 / 1.362
        self.detail_report = self.env.ref("tenenet_projects.tenenet_pl_report")
        self.summary_report = self.env.ref("tenenet_projects.tenenet_pl_summary_report")
        self.program_a = self.env["tenenet.program"].create({"name": "Program A", "code": "PGA"})
        self.program_b = self.env["tenenet.program"].create({"name": "Program B", "code": "PGB"})
        self.employee_a = self.env["hr.employee"].create({"name": "Adam Zamestnanec", "work_ratio": 100.0})
        self.employee_b = self.env["hr.employee"].create({"name": "Beata Zamestnanec", "work_ratio": 100.0})

        self.project_a_int = self.env["tenenet.project"].create({
            "name": "International Alpha",
            "program_ids": [(6, 0, self.program_a.ids)],
            "international": True,
        })
        self.project_a_nat = self.env["tenenet.project"].create({
            "name": "National Beta",
            "program_ids": [(6, 0, self.program_a.ids)],
            "international": False,
        })
        self.project_b_nat = self.env["tenenet.project"].create({
            "name": "Program B Project",
            "program_ids": [(6, 0, self.program_b.ids)],
            "international": False,
        })

        self.assignment_a_int = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_a.id,
            "project_id": self.project_a_int.id,
            "allocation_ratio": 40.0,
            "wage_hm": self.base_wage_hm,
        })
        self.assignment_a_nat = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_b.id,
            "project_id": self.project_a_nat.id,
            "allocation_ratio": 30.0,
            "wage_hm": self.base_wage_hm,
        })
        self.assignment_b_nat = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_b.id,
            "project_id": self.project_b_nat.id,
            "allocation_ratio": 30.0,
            "wage_hm": self.base_wage_hm,
        })

    def _column_map(self, line):
        return {column["expression_label"]: column["no_format"] for column in line["columns"]}

    def _get_detail_lines(self, year, program, unfold_all=False):
        options = self.detail_report.get_options({
            "date": {
                "mode": "single",
                "filter": "custom",
                "date_to": f"{year}-12-31",
            },
            "program_ids": [program.id],
        })
        if unfold_all:
            options["unfold_all"] = True
        return self.detail_report._get_lines(options)

    def _get_summary_lines(self, year):
        options = self.summary_report.get_options({
            "date": {
                "mode": "single",
                "filter": "custom",
                "date_to": f"{year}-12-31",
            },
        })
        return self.summary_report._get_lines(options)

    def _find_line(self, lines, name):
        return next(line for line in lines if line["name"] == name)

    def _create_timesheet(self, assignment, period, hours_pp):
        self.env["tenenet.project.timesheet"].create({
            "assignment_id": assignment.id,
            "period": period,
            "hours_pp": hours_pp,
        })

    def _create_receipt(self, project, date_received, amount):
        return self.env["tenenet.project.receipt"].create({
            "project_id": project.id,
            "date_received": date_received,
            "amount": amount,
        })

    def _set_income_override(self, year, project, month, amount):
        override_model = self.env["tenenet.cashflow.global.override"].with_context(grid_anchor=f"{year}-01-01")
        override_model.action_prepare_grid_year()
        rows = self.env["tenenet.cashflow.global.override"].search([
            ("year", "=", year),
            ("row_key", "=", f"income:{project.id}"),
        ])
        rows.write({"amount": 0.0})
        rows.filtered(lambda rec: rec.month == month)[:1].write({"amount": amount})

    def _set_pl_override(self, year, program, row_key, month, amount):
        override_model = self.env["tenenet.pl.program.override"].with_context(grid_anchor=f"{year}-01-01")
        override_model.action_prepare_grid_year()
        self.env["tenenet.pl.program.override"].search([
            ("year", "=", year),
            ("program_id", "=", program.id),
            ("row_key", "=", row_key),
            ("month", "=", month),
        ], limit=1).write({"amount": amount})

    def test_detail_report_matches_workbook_layout_and_formulas(self):
        year = fields.Date.context_today(self).year + 1
        self._create_receipt(self.project_a_int, f"{year}-03-01", 1200.0)
        self._create_receipt(self.project_a_nat, f"{year}-03-01", 600.0)
        self._set_income_override(year, self.project_a_int, 3, 1200.0)
        self._set_income_override(year, self.project_a_nat, 3, 600.0)
        self._create_timesheet(self.assignment_a_int, f"{year}-03-01", 100.0)
        self._create_timesheet(self.assignment_a_nat, f"{year}-04-01", 50.0)
        self._set_pl_override(year, self.program_a, "trzby", 3, 200.0)

        default_lines = self._get_detail_lines(year, self.program_a)
        self.assertEqual([line["name"] for line in default_lines], [
            "Príjmy/výnosy",
            "Projekty medzinárodné",
            "Projekty národné",
            "Tržby",
            "Príjmy spolu",
            "Náklady",
            "Mzdové náklady - program",
            "Stravné a iné",
            "Zisk/strata - vykrytie mzdových nákladov",
            "Admin a MNG náklady",
            "Mzdové N - podporné odd/admin",
            "Mzdové N - management",
            "Prevádzkové náklady",
            "Zisk/strata - za program",
        ])
        prijmy_line = self._find_line(default_lines, "Príjmy/výnosy")
        naklady_line = self._find_line(default_lines, "Náklady")
        self.assertTrue(prijmy_line["unfoldable"])
        self.assertTrue(prijmy_line["unfolded"])
        self.assertEqual(
            prijmy_line["expand_function"],
            "_report_expand_unfoldable_line_tenenet_pl_income_section",
        )
        self.assertTrue(naklady_line["unfoldable"])
        self.assertTrue(naklady_line["unfolded"])

        lines = self._get_detail_lines(year, self.program_a, unfold_all=True)
        self.assertEqual([line["name"] for line in lines], [
            "Príjmy/výnosy",
            "Projekty medzinárodné",
            "International Alpha",
            "Projekty národné",
            "National Beta",
            "Tržby",
            "Príjmy spolu",
            "Náklady",
            "Mzdové náklady - program",
            "Stravné a iné",
            "Zisk/strata - vykrytie mzdových nákladov",
            "Admin a MNG náklady",
            "Mzdové N - podporné odd/admin",
            "Mzdové N - management",
            "Prevádzkové náklady",
            "Zisk/strata - za program",
        ])
        international_section = self._find_line(lines, "Projekty medzinárodné")
        national_section = self._find_line(lines, "Projekty národné")
        self.assertTrue(international_section["unfoldable"])
        self.assertEqual(
            international_section["expand_function"],
            "_report_expand_unfoldable_line_tenenet_pl_international_section",
        )
        self.assertTrue(national_section["unfoldable"])

        international_columns = self._column_map(self._find_line(lines, "International Alpha"))
        national_columns = self._column_map(self._find_line(lines, "National Beta"))
        trzby_columns = self._column_map(self._find_line(lines, "Tržby"))
        income_total_columns = self._column_map(self._find_line(lines, "Príjmy spolu"))
        labor_cost_columns = self._column_map(self._find_line(lines, "Mzdové náklady - program"))
        pre_admin_columns = self._column_map(self._find_line(lines, "Zisk/strata - vykrytie mzdových nákladov"))
        final_columns = self._column_map(self._find_line(lines, "Zisk/strata - za program"))

        self.assertAlmostEqual(international_columns["month_03"], 1200.0, places=2)
        self.assertAlmostEqual(national_columns["month_03"], 600.0, places=2)
        self.assertAlmostEqual(trzby_columns["month_03"], 200.0, places=2)
        self.assertAlmostEqual(income_total_columns["month_03"], 2000.0, places=2)
        self.assertAlmostEqual(labor_cost_columns["month_03"], -100.0, places=2)
        self.assertAlmostEqual(labor_cost_columns["month_04"], -50.0, places=2)
        self.assertAlmostEqual(pre_admin_columns["month_03"], 1900.0, places=2)
        self.assertAlmostEqual(pre_admin_columns["month_04"], -50.0, places=2)
        self.assertAlmostEqual(final_columns["month_03"], 1900.0, places=2)
        self.assertAlmostEqual(final_columns["year_total"], 1850.0, places=2)

    def test_detail_report_uses_effective_cashflow_income_overrides(self):
        year = fields.Date.context_today(self).year + 1
        self._create_receipt(self.project_a_int, f"{year}-03-01", 1200.0)
        override_model = self.env["tenenet.cashflow.global.override"].with_context(grid_anchor=f"{year}-01-01")
        override_model.action_prepare_grid_year()
        self.env["tenenet.cashflow.global.override"].search([
            ("year", "=", year),
            ("row_key", "=", f"income:{self.project_a_int.id}"),
            ("month", "=", 3),
        ], limit=1).write({"amount": 900.0})

        lines = self._get_detail_lines(year, self.program_a, unfold_all=True)
        international_columns = self._column_map(self._find_line(lines, "International Alpha"))
        income_total_columns = self._column_map(self._find_line(lines, "Príjmy spolu"))

        self.assertAlmostEqual(international_columns["month_03"], 900.0, places=2)
        self.assertAlmostEqual(income_total_columns["month_03"], 900.0, places=2)

    def test_pl_override_can_edit_any_report_line(self):
        year = fields.Date.context_today(self).year + 1
        self._create_receipt(self.project_a_int, f"{year}-03-01", 1200.0)
        self._set_income_override(year, self.project_a_int, 3, 1200.0)
        self._create_timesheet(self.assignment_a_int, f"{year}-03-01", 100.0)
        self._set_pl_override(year, self.program_a, f"income:{self.project_a_int.id}", 3, 1500.0)
        self._set_pl_override(year, self.program_a, "labor_cost", 3, -300.0)
        self._set_pl_override(year, self.program_a, "final_result", 3, 777.0)

        lines = self._get_detail_lines(year, self.program_a, unfold_all=True)
        international_columns = self._column_map(self._find_line(lines, "International Alpha"))
        labor_cost_columns = self._column_map(self._find_line(lines, "Mzdové náklady - program"))
        pre_admin_columns = self._column_map(self._find_line(lines, "Zisk/strata - vykrytie mzdových nákladov"))
        final_columns = self._column_map(self._find_line(lines, "Zisk/strata - za program"))

        self.assertAlmostEqual(international_columns["month_03"], 1500.0, places=2)
        self.assertAlmostEqual(labor_cost_columns["month_03"], -300.0, places=2)
        self.assertAlmostEqual(pre_admin_columns["month_03"], 1200.0, places=2)
        self.assertAlmostEqual(final_columns["month_03"], 777.0, places=2)

    def test_international_split_uses_project_checkbox(self):
        year = fields.Date.context_today(self).year + 1
        donor = self.env["tenenet.donor"].create({"name": "International Donor", "donor_type": "international"})
        project = self.env["tenenet.project"].create({
            "name": "Lokálny podľa checkboxu",
            "program_ids": [(6, 0, self.program_a.ids)],
            "donor_id": donor.id,
            "international": False,
        })
        self._create_receipt(project, f"{year}-03-01", 500.0)
        self._set_income_override(year, project, 3, 500.0)

        lines = self._get_detail_lines(year, self.program_a, unfold_all=True)
        line_names = [line["name"] for line in lines]
        self.assertIn("Lokálny podľa checkboxu", line_names)
        self.assertGreater(line_names.index("Lokálny podľa checkboxu"), line_names.index("Projekty národné"))
        self.assertLess(line_names.index("Lokálny podľa checkboxu"), line_names.index("Tržby"))

    def test_summary_report_shows_both_blocks_and_totals(self):
        year = fields.Date.context_today(self).year + 1
        self._create_receipt(self.project_a_int, f"{year}-03-01", 1200.0)
        self._create_receipt(self.project_b_nat, f"{year}-03-01", 300.0)
        self._set_income_override(year, self.project_a_int, 3, 1200.0)
        self._set_income_override(year, self.project_b_nat, 3, 300.0)
        self._create_timesheet(self.assignment_a_int, f"{year}-03-01", 100.0)
        self._create_timesheet(self.assignment_b_nat, f"{year}-03-01", 50.0)
        self._set_pl_override(year, self.program_a, "trzby", 3, 200.0)

        lines = self._get_summary_lines(year)
        line_names = [line["name"] for line in lines]
        self.assertEqual(line_names[0], "P&L bez admin costs")
        self.assertIn("Program A", line_names)
        self.assertIn("Program B", line_names)
        self.assertIn("P&L total", line_names)
        self.assertEqual(line_names.count("Spolu"), 2)

        pre_admin_start = line_names.index("P&L bez admin costs")
        final_start = line_names.index("P&L total")
        pre_admin_lines = lines[pre_admin_start + 1:final_start]
        final_lines = lines[final_start + 1:]

        pre_admin_a = self._column_map(next(line for line in pre_admin_lines if line["name"] == "Program A"))
        pre_admin_b = self._column_map(next(line for line in pre_admin_lines if line["name"] == "Program B"))
        pre_admin_total = self._column_map(pre_admin_lines[-1])
        final_a = self._column_map(next(line for line in final_lines if line["name"] == "Program A"))
        final_total = self._column_map(final_lines[-1])

        self.assertAlmostEqual(pre_admin_a["month_03"], 1300.0, places=2)
        self.assertAlmostEqual(pre_admin_b["month_03"], 250.0, places=2)
        self.assertAlmostEqual(pre_admin_total["month_03"], 1550.0, places=2)
        self.assertAlmostEqual(final_a["month_03"], 1300.0, places=2)
        self.assertAlmostEqual(final_total["year_total"], 1550.0, places=2)

    def test_selected_program_without_data_still_renders_zero_rows(self):
        year = fields.Date.context_today(self).year + 1
        program_c = self.env["tenenet.program"].create({"name": "Program C", "code": "PGC"})

        lines = self._get_detail_lines(year, program_c, unfold_all=True)
        final_columns = self._column_map(self._find_line(lines, "Zisk/strata - za program"))

        self.assertAlmostEqual(final_columns["month_01"], 0.0, places=2)
        self.assertAlmostEqual(final_columns["year_total"], 0.0, places=2)

    def test_program_override_grid_prepares_year_rows(self):
        year = fields.Date.context_today(self).year + 1
        self._create_receipt(self.project_a_int, f"{year}-03-01", 1200.0)
        self._create_receipt(self.project_a_nat, f"{year}-03-01", 600.0)
        self._set_income_override(year, self.project_a_int, 3, 1200.0)
        self._set_income_override(year, self.project_a_nat, 3, 600.0)
        self.env["tenenet.pl.program.override"].with_context(grid_anchor=f"{year}-01-01").action_prepare_grid_year()

        overrides = self.env["tenenet.pl.program.override"].search([("year", "=", year)])
        program_a_rows = overrides.filtered(lambda rec: rec.program_id == self.program_a)
        program_b_rows = overrides.filtered(lambda rec: rec.program_id == self.program_b)

        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == f"income:{self.project_a_int.id}")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == f"income:{self.project_a_nat.id}")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == "trzby")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == "prijmy_spolu")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == "labor_cost")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == "final_result")), 12)
        self.assertEqual(len(program_b_rows.filtered(lambda rec: rec.row_key == "trzby")), 12)

        report_line_names = {line["name"] for line in self._get_detail_lines(year, self.program_a, unfold_all=True)}
        override_row_labels = set(program_a_rows.mapped("row_label"))
        self.assertTrue(report_line_names.issubset(override_row_labels))
