from odoo import fields
from odoo.exceptions import UserError
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

        self.project_a = self.env["tenenet.project"].create({
            "name": "Projekt Alpha",
            "program_ids": [(6, 0, self.program_a.ids)],
            "reporting_program_id": self.program_a.id,
            "international": True,
        })
        self.project_b = self.env["tenenet.project"].create({
            "name": "Projekt Beta",
            "program_ids": [(6, 0, self.program_b.ids)],
            "reporting_program_id": self.program_b.id,
        })
        self.multi_project = self.env["tenenet.project"].create({
            "name": "Projekt Multi",
            "program_ids": [(6, 0, (self.program_a | self.program_b).ids)],
            "reporting_program_id": self.program_a.id,
        })

        self.assignment_a = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_a.id,
            "project_id": self.project_a.id,
            "allocation_ratio": 40.0,
            "wage_hm": self.base_wage_hm,
        })
        self.assignment_b = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_b.id,
            "project_id": self.project_b.id,
            "allocation_ratio": 30.0,
            "wage_hm": self.base_wage_hm,
        })
        self.assignment_multi = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_b.id,
            "project_id": self.multi_project.id,
            "allocation_ratio": 20.0,
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

    def _create_sales_entry(self, program, period, sale_type, amount):
        return self.env["tenenet.program.sales.entry"].create({
            "program_id": program.id,
            "period": period,
            "sale_type": sale_type,
            "amount": amount,
        })

    def _create_fundraising_entry(self, program, year, month, amount, target_amount=0.0, name="Zbierka"):
        campaign = self.env["tenenet.fundraising.campaign"].create({
            "name": name,
            "program_id": program.id,
            "target_amount": target_amount,
            "date_start": f"{year}-01-01",
        })
        self.env["tenenet.fundraising.entry"].create({
            "campaign_id": campaign.id,
            "date_received": f"{year}-{month:02d}-01",
            "amount": amount,
        })
        return campaign

    def _create_operating_pool(self, year, annual_amount):
        pool = self.env["tenenet.operating.cost.pool"].create({
            "year": year,
            "basis_year": year - 1,
            "annual_amount": annual_amount,
        })
        pool.action_rebuild_allocations()
        return pool

    def _set_pl_override(self, year, program, row_key, month, amount):
        override_model = self.env["tenenet.pl.program.override"].with_context(grid_anchor=f"{year}-01-01")
        override_model.action_prepare_grid_year()
        self.env["tenenet.pl.program.override"].search([
            ("year", "=", year),
            ("program_id", "=", program.id),
            ("row_key", "=", row_key),
            ("month", "=", month),
        ], limit=1).write({"amount": amount})

    def test_detail_report_uses_projects_sales_fundraising_and_operating_pool(self):
        year = fields.Date.context_today(self).year + 1
        self._create_receipt(self.project_a, f"{year}-03-01", 1200.0)
        self._create_receipt(self.multi_project, f"{year}-03-01", 300.0)
        self._set_income_override(year, self.project_a, 3, 1200.0)
        self._set_income_override(year, self.multi_project, 3, 300.0)
        self._create_sales_entry(self.program_a, f"{year}-03-01", "cash_register", 200.0)
        self._create_sales_entry(self.program_a, f"{year}-03-01", "invoice", 400.0)
        self._create_fundraising_entry(self.program_a, year, 3, 500.0, target_amount=1000.0, name="Jarná zbierka")
        self._create_timesheet(self.assignment_a, f"{year}-03-01", 100.0)
        self._create_timesheet(self.assignment_multi, f"{year}-04-01", 50.0)
        self._create_operating_pool(year, 1200.0)

        default_lines = self._get_detail_lines(year, self.program_a)
        self.assertEqual([line["name"] for line in default_lines], [
            "Príjmy/výnosy",
            "Projekty",
            "Tržby",
            "Zbierky",
            "Príjmy spolu",
            "Náklady",
            "Mzdové náklady - program",
            "Stravné a iné",
            "Pokrytie mzdových nákladov",
            "Výsledok po mzdových nákladoch",
            "Mzdové N - podporné odd/admin",
            "Mzdové N - management",
            "Prevádzkové náklady",
            "Výsledok programu",
        ])

        lines = self._get_detail_lines(year, self.program_a, unfold_all=True)
        self.assertEqual([line["name"] for line in lines], [
            "Príjmy/výnosy",
            "Projekty",
            "Projekt Alpha",
            "Projekt Multi",
            "Tržby",
            "Tržby z registračky",
            "Tržby z faktúr",
            "Tržby - neklasifikované",
            "Zbierky",
            "Jarná zbierka",
            "Príjmy spolu",
            "Náklady",
            "Mzdové náklady - program",
            "Projekt Alpha",
            "Projekt Multi",
            "Stravné a iné",
            "Pokrytie mzdových nákladov",
            "Výsledok po mzdových nákladoch",
            "Mzdové N - podporné odd/admin",
            "Mzdové N - management",
            "Prevádzkové náklady",
            "Výsledok programu",
        ])

        project_alpha_columns = self._column_map(self._find_line(lines, "Projekt Alpha"))
        project_multi_income_columns = [
            self._column_map(line)
            for line in lines
            if line["name"] == "Projekt Multi" and line.get("parent_id") == self._find_line(lines, "Projekty")["id"]
        ][0]
        cash_register_columns = self._column_map(self._find_line(lines, "Tržby z registračky"))
        invoice_columns = self._column_map(self._find_line(lines, "Tržby z faktúr"))
        fundraising_columns = self._column_map(self._find_line(lines, "Jarná zbierka"))
        income_total_columns = self._column_map(self._find_line(lines, "Príjmy spolu"))
        labor_cost_columns = self._column_map(self._find_line(lines, "Mzdové náklady - program"))
        coverage_columns = self._column_map(self._find_line(lines, "Pokrytie mzdových nákladov"))
        pre_admin_columns = self._column_map(self._find_line(lines, "Výsledok po mzdových nákladoch"))
        operating_columns = self._column_map(self._find_line(lines, "Prevádzkové náklady"))
        final_columns = self._column_map(self._find_line(lines, "Výsledok programu"))

        self.assertAlmostEqual(project_alpha_columns["month_03"], 1200.0, places=2)
        self.assertAlmostEqual(project_multi_income_columns["month_03"], 300.0, places=2)
        self.assertAlmostEqual(cash_register_columns["month_03"], 200.0, places=2)
        self.assertAlmostEqual(invoice_columns["month_03"], 400.0, places=2)
        self.assertAlmostEqual(fundraising_columns["month_03"], 500.0, places=2)
        self.assertAlmostEqual(income_total_columns["month_03"], 2600.0, places=2)
        self.assertAlmostEqual(labor_cost_columns["month_03"], -100.0, places=2)
        self.assertAlmostEqual(labor_cost_columns["month_04"], -50.0, places=2)
        self.assertAlmostEqual(coverage_columns["month_03"], 2500.0, places=2)
        self.assertAlmostEqual(pre_admin_columns["month_03"], 2500.0, places=2)
        self.assertAlmostEqual(operating_columns["month_03"], -66.67, places=2)
        self.assertAlmostEqual(final_columns["month_03"], 2433.33, places=2)
        self.assertAlmostEqual(final_columns["year_total"], 1650.0, places=2)

    def test_report_uses_reporting_program_not_program_tags(self):
        year = fields.Date.context_today(self).year + 1
        self._create_receipt(self.multi_project, f"{year}-03-01", 250.0)
        self._set_income_override(year, self.multi_project, 3, 250.0)

        lines_a = self._get_detail_lines(year, self.program_a, unfold_all=True)
        lines_b = self._get_detail_lines(year, self.program_b, unfold_all=True)
        line_names_a = [line["name"] for line in lines_a]
        line_names_b = [line["name"] for line in lines_b]

        self.assertIn("Projekt Multi", line_names_a)
        self.assertNotIn("Projekt Multi", line_names_b)

    def test_pl_override_is_limited_to_adjustment_rows(self):
        year = fields.Date.context_today(self).year + 1
        self._create_receipt(self.project_a, f"{year}-03-01", 1200.0)
        self._set_income_override(year, self.project_a, 3, 1200.0)
        self._create_sales_entry(self.program_a, f"{year}-03-01", "cash_register", 200.0)
        self._create_timesheet(self.assignment_a, f"{year}-03-01", 100.0)

        self._set_pl_override(year, self.program_a, "sales_cash_register", 3, 350.0)
        self._set_pl_override(year, self.program_a, "support_admin", 3, -50.0)

        lines = self._get_detail_lines(year, self.program_a, unfold_all=True)
        cash_register_columns = self._column_map(self._find_line(lines, "Tržby z registračky"))
        final_columns = self._column_map(self._find_line(lines, "Výsledok programu"))

        self.assertAlmostEqual(cash_register_columns["month_03"], 350.0, places=2)
        self.assertAlmostEqual(final_columns["month_03"], 1400.0, places=2)

        self.env["tenenet.pl.program.override"].with_context(grid_anchor=f"{year}-01-01").action_prepare_grid_year()
        labor_row = self.env["tenenet.pl.program.override"].search([
            ("year", "=", year),
            ("program_id", "=", self.program_a.id),
            ("row_key", "=", "labor_cost"),
            ("month", "=", 3),
        ], limit=1)
        self.assertFalse(labor_row.is_editable)
        with self.assertRaises(UserError):
            labor_row.write({"amount": 1.0})

    def test_summary_report_aggregates_new_engine(self):
        year = fields.Date.context_today(self).year + 1
        self._create_receipt(self.project_a, f"{year}-03-01", 1200.0)
        self._create_receipt(self.project_b, f"{year}-03-01", 300.0)
        self._set_income_override(year, self.project_a, 3, 1200.0)
        self._set_income_override(year, self.project_b, 3, 300.0)
        self._create_sales_entry(self.program_a, f"{year}-03-01", "cash_register", 200.0)
        self._create_timesheet(self.assignment_a, f"{year}-03-01", 100.0)
        self._create_timesheet(self.assignment_b, f"{year}-03-01", 50.0)

        lines = self._get_summary_lines(year)
        line_names = [line["name"] for line in lines]
        self.assertEqual(line_names[0], "P&L bez admin costs")
        self.assertIn("Program A", line_names)
        self.assertIn("Program B", line_names)
        self.assertIn("P&L total", line_names)

        pre_admin_start = line_names.index("P&L bez admin costs")
        final_start = line_names.index("P&L total")
        pre_admin_lines = lines[pre_admin_start + 1:final_start]
        final_lines = lines[final_start + 1:]

        pre_admin_a = self._column_map(next(line for line in pre_admin_lines if line["name"] == "Program A"))
        pre_admin_b = self._column_map(next(line for line in pre_admin_lines if line["name"] == "Program B"))
        final_total = self._column_map(final_lines[-1])

        self.assertAlmostEqual(pre_admin_a["month_03"], 1300.0, places=2)
        self.assertAlmostEqual(pre_admin_b["month_03"], 250.0, places=2)
        self.assertAlmostEqual(final_total["year_total"], 1550.0, places=2)

    def test_program_override_grid_prepares_new_row_set(self):
        year = fields.Date.context_today(self).year + 1
        self._create_sales_entry(self.program_a, f"{year}-03-01", "cash_register", 100.0)
        self.env["tenenet.pl.program.override"].with_context(grid_anchor=f"{year}-01-01").action_prepare_grid_year()

        overrides = self.env["tenenet.pl.program.override"].search([("year", "=", year)])
        program_a_rows = overrides.filtered(lambda rec: rec.program_id == self.program_a)

        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == "sales_cash_register")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == "sales_invoice")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == "fundraising_total")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == "operating")), 12)
        self.assertNotIn("Projekty medzinárodné", set(program_a_rows.mapped("row_label")))
        self.assertNotIn("Projekty národné", set(program_a_rows.mapped("row_label")))
        self.assertIn("Tržby z registračky", set(program_a_rows.mapped("row_label")))
        self.assertIn("Výsledok programu", set(program_a_rows.mapped("row_label")))

    def test_result_rows_are_visible_but_not_editable(self):
        year = fields.Date.context_today(self).year + 1
        self.env["tenenet.pl.program.override"].with_context(grid_anchor=f"{year}-01-01").action_prepare_grid_year()
        result_row = self.env["tenenet.pl.program.override"].search([
            ("year", "=", year),
            ("program_id", "=", self.program_a.id),
            ("row_key", "=", "final_result"),
            ("month", "=", 3),
        ], limit=1)

        self.assertFalse(result_row.is_editable)
        with self.assertRaises(UserError):
            result_row.write({"amount": 1.0})
