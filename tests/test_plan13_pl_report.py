from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan13PLReport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.base_wage_hm = 1.0
        self.detail_report = self.env.ref("tenenet_projects.tenenet_pl_report")
        self.summary_report = self.env.ref("tenenet_projects.tenenet_pl_summary_report")
        self.admin_program = self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1)
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
            "program_id": self.program_a.id,
            "allocation_ratio": 40.0,
            "wage_hm": self.base_wage_hm,
        })
        self.assignment_b = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_b.id,
            "project_id": self.project_b.id,
            "program_id": self.program_b.id,
            "allocation_ratio": 30.0,
            "wage_hm": self.base_wage_hm,
        })
        self.assignment_multi = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_b.id,
            "project_id": self.multi_project.id,
            "program_id": self.program_a.id,
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

    def _create_budget_line(self, project, year, budget_type, program, name, amount):
        if budget_type == "pausal":
            program = self.admin_program
        return self.env["tenenet.project.budget.line"].create({
            "project_id": project.id,
            "year": year,
            "budget_type": budget_type,
            "program_id": program.id,
            "name": name,
            "amount": amount,
        })

    def _create_budget_line_months(self, budget_line, month_amounts):
        budget_line.set_month_amounts({str(month): amount for month, amount in month_amounts.items()})

    def _set_pl_override(self, year, program, row_key, month, amount):
        override_model = self.env["tenenet.pl.program.override"].with_context(grid_anchor=f"{year}-01-01")
        override_model.action_prepare_grid_year()
        self.env["tenenet.pl.program.override"].search([
            ("year", "=", year),
            ("program_id", "=", program.id),
            ("row_key", "=", row_key),
            ("month", "=", month),
        ], limit=1).write({"amount": amount})

    def _create_user(self, login, group_ids):
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": login,
            "login": login,
            "email": f"{login}@example.com",
            "company_id": self.env.company.id,
            "company_ids": [Command.set([self.env.company.id])],
            "group_ids": [Command.set(group_ids)],
        })

    def _create_hr_expense_type(self, name):
        product = self.env["product.product"].create({
            "name": f"{name} produkt",
            "type": "service",
            "can_be_expensed": True,
        })
        return self.env["tenenet.expense.type.config"].create({
            "name": name,
            "hr_expense_product_id": product.id,
        })

    def _create_project_hr_expense(self, employee, project, config, amount, expense_date):
        return self.env["hr.expense"].create({
            "name": f"{config.name} test",
            "employee_id": employee.id,
            "date": expense_date,
            "total_amount_currency": amount,
            "tenenet_project_id": project.id,
            "tenenet_expense_type_config_id": config.id,
        })

    def test_detail_report_uses_projects_sales_fundraising_and_operating_pool(self):
        year = fields.Date.context_today(self).year + 1
        project_a_income = self._create_budget_line(self.project_a, year, "other", self.program_a, "Projektový príjem A", 1200.0)
        project_multi_income = self._create_budget_line(self.multi_project, year, "other", self.program_a, "Projektový príjem Multi", 300.0)
        self._create_budget_line_months(project_a_income, {3: 1200.0})
        self._create_budget_line_months(project_multi_income, {3: 300.0})
        self._create_sales_entry(self.program_a, f"{year}-03-01", "cash_register", 200.0)
        self._create_sales_entry(self.program_a, f"{year}-03-01", "invoice", 400.0)
        self._create_fundraising_entry(self.program_a, year, 3, 500.0, target_amount=1000.0, name="Jarná zbierka")
        self._create_timesheet(self.assignment_a, f"{year}-03-01", 100.0)
        self._create_timesheet(self.assignment_multi, f"{year}-04-01", 50.0)
        pool = self._create_operating_pool(year, 1200.0)

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
            "Prevádzkové náklady",
            "Výsledok programu",
        ])

        lines = self._get_detail_lines(year, self.program_a, unfold_all=True)
        self.assertEqual([line["name"] for line in lines], [
            "Príjmy/výnosy",
            "Projekty",
            "Projekt Alpha",
            "Iné rozpočty",
            "Projekt Multi",
            "Iné rozpočty",
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
        expected_operating_month_03 = -sum(
            pool.allocation_ids.filtered(
                lambda rec: rec.program_id == self.program_a and rec.month == 3
            ).mapped("amount")
        )
        expected_operating_total = -sum(
            pool.allocation_ids.filtered(
                lambda rec: rec.program_id == self.program_a
            ).mapped("amount")
        )
        self.assertAlmostEqual(operating_columns["month_03"], expected_operating_month_03, places=2)
        self.assertAlmostEqual(
            final_columns["month_03"],
            pre_admin_columns["month_03"] + expected_operating_month_03,
            places=2,
        )
        self.assertAlmostEqual(
            final_columns["year_total"],
            sum(final_columns[f"month_{month:02d}"] for month in range(1, 13)),
            places=2,
        )
        self.assertAlmostEqual(operating_columns["year_total"], expected_operating_total, places=2)

    def test_admin_tenenet_detail_uses_labor_mgmt_override_when_present(self):
        year = fields.Date.context_today(self).year + 1
        self._set_pl_override(year, self.admin_program, "labor_mgmt", 3, -100.0)

        lines = self._get_detail_lines(year, self.admin_program, unfold_all=True)
        header_columns = self._column_map(self._find_line(lines, "Mzdové náklady administratívy"))

        self.assertAlmostEqual(header_columns["month_03"], -100.0, places=2)

    def test_report_uses_reporting_program_not_program_tags(self):
        year = fields.Date.context_today(self).year + 1
        project_multi_income = self._create_budget_line(self.multi_project, year, "other", self.program_a, "Projektový príjem Multi", 250.0)
        self._create_budget_line_months(project_multi_income, {3: 250.0})

        lines_a = self._get_detail_lines(year, self.program_a, unfold_all=True)
        lines_b = self._get_detail_lines(year, self.program_b, unfold_all=True)
        line_names_a = [line["name"] for line in lines_a]
        line_names_b = [line["name"] for line in lines_b]

        self.assertIn("Projekt Multi", line_names_a)
        self.assertNotIn("Projekt Multi", line_names_b)

    def test_pl_override_is_limited_to_adjustment_rows(self):
        year = fields.Date.context_today(self).year + 1
        project_a_income = self._create_budget_line(self.project_a, year, "other", self.program_a, "Projektový príjem A", 1200.0)
        self._create_budget_line_months(project_a_income, {3: 1200.0})
        self._create_sales_entry(self.program_a, f"{year}-03-01", "cash_register", 200.0)
        self._create_timesheet(self.assignment_a, f"{year}-03-01", 100.0)

        self._set_pl_override(year, self.program_a, "sales_cash_register", 3, 350.0)
        self._set_pl_override(year, self.program_a, "admin_tenenet_cost", 3, -50.0)

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

    def test_project_income_override_row_updates_program_report(self):
        year = fields.Date.context_today(self).year + 1
        project_a_income = self._create_budget_line(self.project_a, year, "other", self.program_a, "Projektový príjem A", 1200.0)
        self._create_budget_line_months(project_a_income, {3: 1200.0})

        self._set_pl_override(year, self.program_a, f"income:{self.project_a.id}", 3, 1500.0)

        lines = self._get_detail_lines(year, self.program_a, unfold_all=True)
        project_alpha_columns = self._column_map(self._find_line(lines, "Projekt Alpha"))
        income_total_columns = self._column_map(self._find_line(lines, "Príjmy spolu"))

        self.assertAlmostEqual(project_alpha_columns["month_03"], 1500.0, places=2)
        self.assertAlmostEqual(income_total_columns["month_03"], 1500.0, places=2)

    def test_summary_report_aggregates_new_engine(self):
        year = fields.Date.context_today(self).year + 1
        project_a_income = self._create_budget_line(self.project_a, year, "other", self.program_a, "Projektový príjem A", 1200.0)
        project_b_income = self._create_budget_line(self.project_b, year, "other", self.program_b, "Projektový príjem B", 300.0)
        self._create_budget_line_months(project_a_income, {3: 1200.0})
        self._create_budget_line_months(project_b_income, {3: 300.0})
        self._create_sales_entry(self.program_a, f"{year}-03-01", "cash_register", 200.0)
        self._create_timesheet(self.assignment_a, f"{year}-03-01", 100.0)
        self._create_timesheet(self.assignment_b, f"{year}-03-01", 50.0)

        lines = self._get_summary_lines(year)
        line_names = [line["name"] for line in lines]
        self.assertEqual(line_names[0], "Mzdové náklady")
        self.assertIn("Mzdové náklady", line_names)
        self.assertIn("Program A", line_names)
        self.assertIn("Program B", line_names)
        self.assertIn("P&L total", line_names)

        labor_start = line_names.index("Mzdové náklady")
        pre_admin_start = line_names.index("P&L bez admin costs")
        final_start = line_names.index("P&L total")
        labor_lines = lines[labor_start + 1:pre_admin_start]
        pre_admin_lines = lines[pre_admin_start + 1:final_start]
        final_lines = lines[final_start + 1:]

        labor_a = self._column_map(next(line for line in labor_lines if line["name"] == "Program A"))
        pre_admin_a = self._column_map(next(line for line in pre_admin_lines if line["name"] == "Program A"))
        pre_admin_b = self._column_map(next(line for line in pre_admin_lines if line["name"] == "Program B"))
        final_total = self._column_map(final_lines[-1])

        self.assertAlmostEqual(labor_a["month_03"], -100.0, places=2)
        self.assertAlmostEqual(pre_admin_a["month_03"], 1300.0, places=2)
        self.assertAlmostEqual(pre_admin_b["month_03"], 250.0, places=2)
        self.assertAlmostEqual(final_total["year_total"], 1550.0, places=2)

    def test_program_override_grid_prepares_new_row_set(self):
        year = fields.Date.context_today(self).year + 1
        self._create_sales_entry(self.program_a, f"{year}-03-01", "cash_register", 100.0)
        self.env["tenenet.pl.program.override"].with_context(grid_anchor=f"{year}-01-01").action_prepare_grid_year()

        overrides = self.env["tenenet.pl.program.override"].search([("year", "=", year)])
        program_a_rows = overrides.filtered(lambda rec: rec.program_id == self.program_a)

        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == f"income:{self.project_a.id}")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == f"income:{self.multi_project.id}")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == "sales_cash_register")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == "sales_invoice")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == "fundraising_total")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == "admin_tenenet_cost")), 12)
        self.assertEqual(len(program_a_rows.filtered(lambda rec: rec.row_key == "operating")), 12)
        self.assertNotIn("Projekty medzinárodné", set(program_a_rows.mapped("row_label")))
        self.assertNotIn("Projekty národné", set(program_a_rows.mapped("row_label")))
        self.assertIn("Tržby z registračky", set(program_a_rows.mapped("row_label")))
        self.assertIn("Výsledok programu", set(program_a_rows.mapped("row_label")))
        self.assertNotIn("Mzdové N - management", set(program_a_rows.mapped("row_label")))
        self.assertNotIn("Mzdové N - podporné odd/admin", set(program_a_rows.mapped("row_label")))

    def test_program_override_grid_seeds_project_rows_without_income(self):
        year = fields.Date.context_today(self).year + 1
        self.env["tenenet.pl.program.override"].with_context(grid_anchor=f"{year}-01-01").action_prepare_grid_year()

        overrides = self.env["tenenet.pl.program.override"].search([
            ("year", "=", year),
            ("program_id", "=", self.program_a.id),
            ("row_key", "=", f"income:{self.project_a.id}"),
        ])

        self.assertEqual(len(overrides), 12)
        self.assertEqual(set(overrides.mapped("project_label")), {self.project_a.display_name})
        self.assertTrue(all(overrides.mapped("is_editable")))

    def test_program_override_editable_only_context_hides_calculated_rows(self):
        year = fields.Date.context_today(self).year + 1
        override_model = self.env["tenenet.pl.program.override"].with_context(grid_anchor=f"{year}-01-01")
        override_model.action_prepare_grid_year()

        editable_rows = self.env["tenenet.pl.program.override"].with_context(
            pl_program_override_editable_only=True
        ).search([("year", "=", year), ("program_id", "=", self.program_a.id)])

        self.assertTrue(editable_rows)
        self.assertTrue(all(editable_rows.mapped("is_editable")))
        self.assertIn("Tržby z registračky", set(editable_rows.mapped("row_label")))
        self.assertIn("Admin TENENET náklady", set(editable_rows.mapped("row_label")))
        self.assertIn(self.project_a.display_name, " ".join(editable_rows.mapped("project_label")))
        self.assertIn("Projekty", set(editable_rows.mapped("row_label")))
        self.assertNotIn("Výsledok programu", set(editable_rows.mapped("row_label")))

    def test_program_override_grid_row_label_includes_project_when_present(self):
        row = self.env["tenenet.pl.program.override"].create({
            "program_id": self.program_a.id,
            "period": f"{fields.Date.context_today(self).year + 1}-01-01",
            "row_key": "test_project_label",
            "row_label": "Projekty",
            "project_label": "Projekt Alpha",
            "amount": 0.0,
            "currency_id": self.env.company.currency_id.id,
        })

        self.assertEqual(row.grid_row_label, "Projekt Alpha / Projekty")

    def test_admin_tenenet_uses_dedicated_income_and_expense_sections(self):
        year = fields.Date.context_today(self).year + 1
        self._create_budget_line(self.project_a, year, "pausal", self.program_a, "Projektový paušál A", 240.0)
        self.env["tenenet.internal.expense"].create({
            "employee_id": self.employee_a.id,
            "period": f"{year}-03-01",
            "category": "expense",
            "expense_amount": 100.0,
        })

        admin_lines = self._get_detail_lines(year, self.admin_program, unfold_all=True)
        program_lines = self._get_detail_lines(year, self.program_a, unfold_all=True)

        admin_project_columns = self._column_map(self._find_line(admin_lines, "Projekt Alpha"))
        non_project_columns = self._column_map(self._find_line(admin_lines, "Náklady bez projektov"))
        employee_cost_columns = self._column_map(self._find_line(admin_lines, "Adam Zamestnanec"))
        admin_names = [line["name"] for line in admin_lines]
        program_names = [line["name"] for line in program_lines]

        self.assertIn("Paušály", admin_names)
        self.assertIn("Prevádzkové príjmy", admin_names)
        self.assertIn("Náklady bez projektov", admin_names)
        self.assertNotIn("Tržby", admin_names)
        self.assertNotIn("Zbierky", admin_names)
        self.assertNotIn("Admin TENENET náklady", admin_names)
        self.assertIn("Projektový paušál A", admin_names)
        self.assertIn("Adam Zamestnanec", admin_names)
        self.assertAlmostEqual(admin_project_columns["year_total"], 240.0, places=2)
        self.assertAlmostEqual(non_project_columns["month_03"], -100.0, places=2)
        self.assertAlmostEqual(employee_cost_columns["month_03"], -100.0, places=2)
        self.assertNotIn("Projektový paušál A", program_names)

    def test_program_budget_income_sections_are_added_separately(self):
        year = fields.Date.context_today(self).year + 1
        labor_line = self._create_budget_line(self.project_a, year, "labor", self.program_a, "Mzdový plán", 180.0)
        other_line = self._create_budget_line(self.project_a, year, "other", self.program_a, "Iný plán", 90.0)
        self._create_budget_line_months(labor_line, {3: 100.0, 4: 80.0})
        self._create_budget_line_months(other_line, {3: 60.0})

        lines = self._get_detail_lines(year, self.program_a, unfold_all=True)
        line_names = [line["name"] for line in lines]
        income_total_columns = self._column_map(self._find_line(lines, "Príjmy spolu"))
        project_line = self._find_line(lines, "Projekt Alpha")
        project_columns = self._column_map(project_line)
        labor_budget_columns = self._column_map(
            next(line for line in lines if line["name"] == "Mzdové rozpočty" and line.get("parent_id") == project_line["id"])
        )
        other_budget_columns = self._column_map(
            next(line for line in lines if line["name"] == "Iné rozpočty" and line.get("parent_id") == project_line["id"])
        )

        self.assertNotIn("Projekt Alpha / Mzdový plán", line_names)
        self.assertNotIn("Projekt Alpha / Iný plán", line_names)
        self.assertAlmostEqual(project_columns["month_03"], 160.0, places=2)
        self.assertNotIn("Príjmy projektu", [
            line["name"] for line in lines if line.get("parent_id") == project_line["id"]
        ])
        self.assertAlmostEqual(labor_budget_columns["month_03"], 100.0, places=2)
        self.assertAlmostEqual(other_budget_columns["month_03"], 60.0, places=2)
        self.assertAlmostEqual(labor_budget_columns["month_04"], 80.0, places=2)
        self.assertAlmostEqual(income_total_columns["month_03"], 160.0, places=2)

    def test_admin_tenenet_groups_labor_by_project_and_employee(self):
        year = fields.Date.context_today(self).year + 1
        self.env["tenenet.internal.expense"].create({
            "employee_id": self.employee_a.id,
            "period": f"{year}-03-01",
            "category": "wage",
            "source_assignment_id": self.assignment_a.id,
            "wage_hm": self.assignment_a.wage_hm,
            "cost_hm": 100.0,
        })
        self.env["tenenet.internal.expense"].create({
            "employee_id": self.employee_b.id,
            "period": f"{year}-03-01",
            "category": "wage",
            "source_assignment_id": self.assignment_b.id,
            "wage_hm": self.assignment_b.wage_hm,
            "cost_hm": 50.0,
        })

        lines = self._get_detail_lines(year, self.admin_program, unfold_all=True)
        labor_columns = self._column_map(self._find_line(lines, "Mzdové náklady"))
        alpha_columns = self._column_map(self._find_line(lines, "Projekt Alpha"))
        beta_columns = self._column_map(self._find_line(lines, "Projekt Beta"))
        adam_columns = self._column_map(self._find_line(lines, "Adam Zamestnanec"))
        beata_columns = self._column_map(self._find_line(lines, "Beata Zamestnanec"))

        self.assertAlmostEqual(labor_columns["month_03"], -150.0, places=2)
        self.assertAlmostEqual(alpha_columns["month_03"], -100.0, places=2)
        self.assertAlmostEqual(beta_columns["month_03"], -50.0, places=2)
        self.assertAlmostEqual(adam_columns["month_03"], -100.0, places=2)
        self.assertAlmostEqual(beata_columns["month_03"], -50.0, places=2)

    def test_admin_tenenet_does_not_show_fully_covered_project_labor(self):
        year = fields.Date.context_today(self).year + 1
        self._create_timesheet(self.assignment_a, f"{year}-03-01", 100.0)

        lines = self._get_detail_lines(year, self.admin_program, unfold_all=True)
        line_names = [line["name"] for line in lines]
        labor_columns = self._column_map(self._find_line(lines, "Mzdové náklady"))

        self.assertAlmostEqual(labor_columns["month_03"], 0.0, places=2)
        self.assertNotIn("Projekt Alpha", line_names)
        self.assertNotIn("Adam Zamestnanec", line_names)

    def test_program_and_admin_split_wage_cap_excess_by_hm(self):
        year = fields.Date.context_today(self).year + 1
        self.assignment_a.write({
            "wage_hm": 10.0,
            "max_monthly_wage_hm": 700.0,
        })
        self._create_timesheet(self.assignment_a, f"{year}-03-01", 90.0)

        program_lines = self._get_detail_lines(year, self.program_a, unfold_all=True)
        admin_lines = self._get_detail_lines(year, self.admin_program, unfold_all=True)

        program_labor = self._column_map(self._find_line(program_lines, "Mzdové náklady - program"))
        project_labor = self._column_map(self._find_line(program_lines, "Projekt Alpha"))
        program_admin_cost = self._column_map(self._find_line(program_lines, "Admin TENENET náklady"))
        admin_labor = self._column_map(self._find_line(admin_lines, "Mzdové náklady"))
        admin_project = self._column_map(self._find_line(admin_lines, "Projekt Alpha"))
        admin_employee = self._column_map(self._find_line(admin_lines, "Adam Zamestnanec"))

        self.assertAlmostEqual(program_labor["month_03"], -700.0, places=2)
        self.assertAlmostEqual(project_labor["month_03"], -700.0, places=2)
        self.assertAlmostEqual(program_admin_cost["month_03"], -200.0, places=2)
        self.assertAlmostEqual(admin_labor["month_03"], -200.0, places=2)
        self.assertAlmostEqual(admin_project["month_03"], -200.0, places=2)
        self.assertAlmostEqual(admin_employee["month_03"], -200.0, places=2)

    def test_program_stravne_uses_covered_hr_expenses_and_admin_gets_internal_remainder(self):
        year = fields.Date.context_today(self).year + 1
        travel_type = self._create_hr_expense_type("Cestovné")
        self.project_a.allowed_expense_type_ids = [(0, 0, {
            "config_id": travel_type.id,
            "name": travel_type.name,
            "max_amount": 100.0,
        })]
        self._create_project_hr_expense(
            self.employee_a,
            self.project_a,
            travel_type,
            150.0,
            f"{year}-04-01",
        )

        program_lines = self._get_detail_lines(year, self.program_a, unfold_all=True)
        admin_lines = self._get_detail_lines(year, self.admin_program, unfold_all=True)

        stravne_columns = self._column_map(self._find_line(program_lines, "Stravné a iné"))
        program_admin_cost = self._column_map(self._find_line(program_lines, "Admin TENENET náklady"))
        admin_labor = self._column_map(self._find_line(admin_lines, "Mzdové náklady"))
        admin_project = self._column_map(self._find_line(admin_lines, "Projekt Alpha"))

        self.assertAlmostEqual(stravne_columns["month_04"], -100.0, places=2)
        self.assertAlmostEqual(program_admin_cost["month_04"], -50.0, places=2)
        self.assertAlmostEqual(admin_labor["month_04"], -50.0, places=2)
        self.assertAlmostEqual(admin_project["month_04"], -50.0, places=2)

    def test_program_labor_keeps_covered_leave_and_admin_gets_uncovered_leave(self):
        year = fields.Date.context_today(self).year + 1
        self.env["tenenet.project.timesheet"].with_context(from_hr_leave_sync=True).create({
            "assignment_id": self.assignment_a.id,
            "period": f"{year}-03-01",
            "hours_vacation": 8.0,
        })
        self.env["tenenet.internal.expense"].create({
            "employee_id": self.employee_a.id,
            "period": f"{year}-04-01",
            "category": "leave",
            "source_assignment_id": self.assignment_a.id,
            "hour_type": "vacation",
            "hours": 4.0,
            "wage_hm": self.assignment_a.wage_hm,
        })

        program_lines = self._get_detail_lines(year, self.program_a, unfold_all=True)
        admin_lines = self._get_detail_lines(year, self.admin_program, unfold_all=True)

        program_labor = self._column_map(self._find_line(program_lines, "Mzdové náklady - program"))
        program_admin_cost = self._column_map(self._find_line(program_lines, "Admin TENENET náklady"))
        admin_labor = self._column_map(self._find_line(admin_lines, "Mzdové náklady"))

        self.assertAlmostEqual(program_labor["month_03"], -8.0, places=2)
        self.assertAlmostEqual(program_labor["month_04"], 0.0, places=2)
        self.assertAlmostEqual(program_admin_cost["month_04"], -4.0, places=2)
        self.assertAlmostEqual(admin_labor["month_04"], -4.0, places=2)

    def test_admin_tenenet_separates_management_labor(self):
        year = fields.Date.context_today(self).year + 1
        self.employee_b.is_mgmt = True
        self.env["tenenet.internal.expense"].create({
            "employee_id": self.employee_a.id,
            "period": f"{year}-03-01",
            "category": "expense",
            "expense_amount": 100.0,
        })
        self.env["tenenet.internal.expense"].create({
            "employee_id": self.employee_b.id,
            "period": f"{year}-03-01",
            "category": "expense",
            "expense_amount": 200.0,
        })

        lines = self._get_detail_lines(year, self.admin_program, unfold_all=True)
        non_project_columns = self._column_map(self._find_line(lines, "Náklady bez projektov"))
        mgmt_columns = self._column_map(self._find_line(lines, "Mzdové náklady administratívy"))
        line_names = [line["name"] for line in lines]

        self.assertAlmostEqual(non_project_columns["month_03"], -100.0, places=2)
        self.assertAlmostEqual(mgmt_columns["month_03"], -200.0, places=2)
        self.assertIn("Adam Zamestnanec", line_names)
        self.assertNotIn("Beata Zamestnanec", [
            line["name"]
            for line in lines
            if line.get("parent_id") == self._find_line(lines, "Náklady bez projektov")["id"]
        ])

    def test_current_year_sales_prediction_fills_future_months_and_respects_manual_override(self):
        today = fields.Date.context_today(self)
        if today.month == 1:
            self.skipTest("Prediction test requires at least one past month.")

        if today.month == 2:
            self.skipTest("Split prediction test requires at least two historical months.")

        self._create_sales_entry(self.program_a, f"{today.year}-{today.month - 1:02d}-01", "cash_register", 120.0)
        self._create_sales_entry(self.program_a, f"{today.year}-{today.month - 2:02d}-01", "cash_register", 240.0)
        expected = 180.0

        lines = self._get_detail_lines(today.year, self.program_a, unfold_all=True)
        cash_register_real = self._column_map(self._find_line(lines, "Tržby z registračky - Realita"))
        cash_register_predicted = self._column_map(self._find_line(lines, "Tržby z registračky - Predikcia"))
        income_total_predicted = self._column_map(self._find_line(lines, "Príjmy spolu - Predikcia"))
        current_label = f"month_{today.month:02d}"
        self.assertAlmostEqual(cash_register_real[current_label], 0.0, places=2)
        self.assertAlmostEqual(cash_register_predicted[current_label], expected, places=2)
        self.assertAlmostEqual(income_total_predicted[current_label], expected, places=2)

        self._set_pl_override(today.year, self.program_a, "sales_cash_register", today.month, 999.0)
        lines = self._get_detail_lines(today.year, self.program_a, unfold_all=True)
        cash_register_predicted = self._column_map(self._find_line(lines, "Tržby z registračky - Predikcia"))
        self.assertAlmostEqual(cash_register_predicted[current_label], 999.0, places=2)

    def test_current_year_sales_prediction_does_not_fill_with_single_historical_month(self):
        today = fields.Date.context_today(self)
        if today.month == 1:
            self.skipTest("Prediction test requires at least one past month.")

        self._create_sales_entry(self.program_a, f"{today.year}-{today.month - 1:02d}-01", "cash_register", 120.0)

        lines = self._get_detail_lines(today.year, self.program_a, unfold_all=True)
        cash_register_columns = self._column_map(self._find_line(lines, "Tržby z registračky"))
        current_label = f"month_{today.month:02d}"

        self.assertAlmostEqual(cash_register_columns[current_label], 0.0, places=2)

    def test_current_year_project_prediction_ignores_receipts_and_uses_planner_budgets_only(self):
        today = fields.Date.context_today(self)
        if today.month <= 2:
            self.skipTest("Planner prediction test requires at least two historical months.")

        self._create_receipt(self.project_a, f"{today.year}-{today.month - 1:02d}-01", 100000.0)
        project_a_income = self._create_budget_line(
            self.project_a,
            today.year,
            "other",
            self.program_a,
            "Projektový príjem A",
            6000.0,
        )
        self._create_budget_line_months(project_a_income, {
            today.month - 2: 3000.0,
            today.month - 1: 3000.0,
        })

        lines = self._get_detail_lines(today.year, self.program_a, unfold_all=True)
        project_real = self._column_map(self._find_line(lines, "Projekt Alpha - Realita"))
        project_predicted = self._column_map(self._find_line(lines, "Projekt Alpha - Predikcia"))
        income_total_predicted = self._column_map(self._find_line(lines, "Príjmy spolu - Predikcia"))
        current_label = f"month_{today.month:02d}"

        self.assertAlmostEqual(project_real[current_label], 0.0, places=2)
        self.assertAlmostEqual(project_predicted[current_label], 3000.0, places=2)
        self.assertAlmostEqual(income_total_predicted[current_label], 3000.0, places=2)

    def test_get_garant_projects_excludes_internal_project_for_manager_and_garant(self):
        manager_group = self.env.ref("tenenet_projects.group_tenenet_manager")
        garant_group = self.env.ref("tenenet_projects.group_tenenet_garant_pm")
        manager_user = self._create_user("timesheet.manager", [manager_group.id])
        garant_user = self._create_user("timesheet.garant", [garant_group.id])
        garant_employee = self.env["hr.employee"].create({
            "name": "Garant Employee",
            "user_id": garant_user.id,
        })
        public_project = self.env["tenenet.project"].create({
            "name": "Garant Project",
            "program_ids": [(6, 0, self.program_a.ids)],
            "reporting_program_id": self.program_a.id,
            "odborny_garant_id": garant_employee.id,
        })
        internal_project = self.env["tenenet.project"].search([("is_tenenet_internal", "=", True)], limit=1)
        internal_project.write({"odborny_garant_id": garant_employee.id})

        matrix_model = self.env["tenenet.project.timesheet.matrix"]
        manager_projects = matrix_model.with_user(manager_user).get_garant_projects()
        garant_projects = matrix_model.with_user(garant_user).get_garant_projects()

        self.assertIn(public_project.id, [project["id"] for project in manager_projects])
        self.assertIn(public_project.id, [project["id"] for project in garant_projects])
        self.assertNotIn(internal_project.id, [project["id"] for project in manager_projects])
        self.assertNotIn(internal_project.id, [project["id"] for project in garant_projects])

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
