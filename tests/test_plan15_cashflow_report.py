from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan15CashflowReport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.report = self.env.ref("tenenet_projects.tenenet_cashflow_report")
        self.program_a = self.env["tenenet.program"].create({"name": "Program A", "code": "PLAN15_A"})
        self.program_b = self.env["tenenet.program"].create({"name": "Program B", "code": "PLAN15_B"})
        self.project_a = self.env["tenenet.project"].create({
            "name": "Projekt A",
            "program_ids": [(6, 0, self.program_a.ids)],
        })
        self.project_b = self.env["tenenet.project"].create({
            "name": "Projekt B",
            "program_ids": [(6, 0, (self.program_a | self.program_b).ids)],
        })
        self.employee = self.env["hr.employee"].create({"name": "Adam Zamestnanec"})
        self.assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.project_a.id,
            "wage_hm": 10.0,
            "wage_ccp": 20.0,
        })

    def _column_map(self, line):
        return {
            column["expression_label"]: column["no_format"]
            for column in line["columns"]
        }

    def _get_lines(self, year):
        options = self.report.get_options({
            "date": {
                "mode": "single",
                "filter": "custom",
                "date_to": f"{year}-12-31",
            },
        })
        return self.report._get_lines(options)

    def _get_allocation_lines(self, year):
        report = self.env.ref("tenenet_projects.tenenet_allocation_report")
        options = report.get_options({
            "date": {
                "mode": "single",
                "filter": "custom",
                "date_to": f"{year}-12-31",
            },
            "employee_ids": [self.employee.id],
        })
        return report._get_lines(options)

    def _find_line(self, lines, project_name):
        return next(line for line in lines if self._column_map(line).get("project_label") == project_name)

    def _find_expense_line(self, lines, project_name):
        return next(
            line
            for line in lines
            if self._column_map(line).get("project_label") == project_name
            and line.get("class") == "cashflow_expense_line"
        )

    def _find_named_line(self, lines, name):
        return next(line for line in lines if self._column_map(line).get("project_label") == name)

    def _find_allocation_line(self, lines, name):
        return next(line for line in lines if line["name"] == name)

    def _create_override_row(self, year, month, row_key, row_label, row_type, amount, program_label=""):
        return self.env["tenenet.cashflow.global.override"].create({
            "period": f"{year}-{month:02d}-01",
            "row_key": row_key,
            "row_label": row_label,
            "row_type": row_type,
            "program_label": program_label,
            "amount": amount,
        })

    def test_receipt_generation_starts_from_received_month(self):
        jan = self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": "2026-01-05",
            "amount": 1200.0,
        })
        feb = self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": "2026-02-05",
            "amount": 1200.0,
        })
        mar = self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": "2026-03-05",
            "amount": 1200.0,
        })

        self.assertEqual(jan.cashflow_ids.mapped("month"), list(range(1, 13)))
        self.assertEqual(feb.cashflow_ids.mapped("month"), list(range(2, 13)))
        self.assertEqual(mar.cashflow_ids.mapped("month"), list(range(3, 13)))

        feb_amounts = {line.month: line.amount for line in feb.cashflow_ids}
        mar_amounts = {line.month: line.amount for line in mar.cashflow_ids}

        self.assertAlmostEqual(feb_amounts[2], 200.0, places=2)
        self.assertAlmostEqual(feb_amounts[3], 100.0, places=2)
        self.assertAlmostEqual(feb_amounts[12], 100.0, places=2)
        self.assertAlmostEqual(sum(feb_amounts.values()), 1200.0, places=2)

        self.assertAlmostEqual(mar_amounts[3], 300.0, places=2)
        self.assertAlmostEqual(mar_amounts[4], 100.0, places=2)
        self.assertAlmostEqual(sum(mar_amounts.values()), 1200.0, places=2)

    def test_receipt_generation_puts_rounding_remainder_in_last_month(self):
        receipt = self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": "2026-01-05",
            "amount": 1000.0,
        })
        amounts = {line.month: line.amount for line in receipt.cashflow_ids}

        self.assertAlmostEqual(amounts[1], 83.33, places=2)
        self.assertAlmostEqual(amounts[12], 83.37, places=2)
        self.assertAlmostEqual(sum(amounts.values()), 1000.0, places=2)

    def test_project_cashflow_receipt_label_uses_slovak_format(self):
        receipt = self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": "2026-01-01",
            "amount": 1000.0,
        })
        cashflow = receipt.cashflow_ids[:1]

        self.assertEqual(cashflow.receipt_label, "1.1.2026 / 1 000 €")

    def test_cashflow_edit_rebalances_last_active_month(self):
        receipt = self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": "2026-03-01",
            "amount": 1200.0,
        })
        march_line = receipt.cashflow_ids.filtered(lambda rec: rec.month == 3)
        december_line = receipt.cashflow_ids.filtered(lambda rec: rec.month == 12)

        march_line.write({"amount": 350.0})

        self.assertAlmostEqual(march_line.amount, 350.0, places=2)
        self.assertAlmostEqual(december_line.amount, 50.0, places=2)
        self.assertAlmostEqual(sum(receipt.cashflow_ids.mapped("amount")), 1200.0, places=2)

    def test_project_cashflow_grid_update_reloads_and_rebalances(self):
        receipt = self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": "2026-03-01",
            "amount": 1200.0,
        })
        march_line = receipt.cashflow_ids.filtered(lambda rec: rec.month == 3)
        december_line = receipt.cashflow_ids.filtered(lambda rec: rec.month == 12)

        action = self.env["tenenet.project.cashflow"].grid_update_cell(
            [("id", "=", march_line.id)],
            "amount",
            50.0,
        )

        self.assertEqual(action, {"type": "ir.actions.client", "tag": "reload"})
        self.assertAlmostEqual(march_line.amount, 350.0, places=2)
        self.assertAlmostEqual(december_line.amount, 50.0, places=2)

    def test_report_uses_row_level_overrides_for_detail_lines(self):
        selected_year = fields.Date.context_today(self).year + 1
        self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": f"{selected_year}-02-01",
            "amount": 1200.0,
        })
        self.env["tenenet.project.receipt"].create({
            "project_id": self.project_b.id,
            "date_received": f"{selected_year}-02-01",
            "amount": 600.0,
        })
        override_model = self.env["tenenet.cashflow.global.override"].with_context(grid_anchor=f"{selected_year}-01-01")
        override_model.action_prepare_grid_year()
        self.env["tenenet.cashflow.global.override"].search([
            ("year", "=", selected_year),
            ("row_key", "=", f"income:{self.project_a.id}"),
            ("month", "=", 2),
        ], limit=1).write({"amount": 700.0})
        self.env["tenenet.cashflow.global.override"].search([
            ("year", "=", selected_year),
            ("row_key", "=", f"income:{self.project_b.id}"),
            ("month", "=", 2),
        ], limit=1).write({"amount": 200.0})

        lines = self._get_lines(selected_year)
        project_a_line = self._find_line(lines, "Projekt A")
        project_b_line = self._find_line(lines, "Projekt B")
        cash_in_line = self._find_named_line(lines, "Cash-IN")

        project_a_columns = self._column_map(project_a_line)
        project_b_columns = self._column_map(project_b_line)
        cash_in_columns = self._column_map(cash_in_line)

        self.assertAlmostEqual(project_a_columns["month_02"], 700.0, places=2)
        self.assertAlmostEqual(project_b_columns["month_02"], 200.0, places=2)
        self.assertAlmostEqual(cash_in_columns["month_02"], 900.0, places=2)
        self.assertEqual(project_b_line["name"], "Program A, Program B")
        self.assertTrue(any(line.get("class") == "cashflow_spacer_line" for line in lines))

    def test_report_uses_project_cashflow_for_future_year(self):
        selected_year = fields.Date.context_today(self).year + 1
        self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": f"{selected_year}-03-01",
            "amount": 1200.0,
        })

        lines = self._get_lines(selected_year)
        project_line = self._find_line(lines, "Projekt A")
        cash_in_line = self._find_named_line(lines, "Cash-IN")

        project_columns = self._column_map(project_line)
        cash_in_columns = self._column_map(cash_in_line)

        self.assertAlmostEqual(project_columns["month_03"], 300.0, places=2)
        self.assertAlmostEqual(cash_in_columns["month_03"], 300.0, places=2)
        self.assertAlmostEqual(cash_in_columns["month_01"], 0.0, places=2)

    def test_prepare_grid_syncs_editable_report_rows(self):
        selected_year = fields.Date.context_today(self).year + 1
        self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": f"{selected_year}-03-01",
            "amount": 1200.0,
        })
        self.env["tenenet.project.expense"].create({
            "project_id": self.project_a.id,
            "allowed_type_id": self.env["tenenet.project.allowed.expense.type"].create({
                "project_id": self.project_a.id,
                "name": "Cesty",
                "max_amount": 0.0,
            }).id,
            "date": f"{selected_year}-03-15",
            "amount": 50.0,
            "description": "Cesta",
        })

        self.env["tenenet.cashflow.global.override"].with_context(grid_anchor=f"{selected_year}-01-01").action_prepare_grid_year()

        overrides = self.env["tenenet.cashflow.global.override"].search([("year", "=", selected_year)])
        self.assertTrue(overrides.filtered(lambda rec: rec.row_key == f"income:{self.project_a.id}" and rec.month == 3))
        self.assertTrue(overrides.filtered(lambda rec: rec.row_key == "salary:mzdy"))
        self.assertTrue(overrides.filtered(lambda rec: rec.row_key == f"expense:{self.project_a.id}" and rec.month == 3))
        self.assertAlmostEqual(
            overrides.filtered(lambda rec: rec.row_key == f"income:{self.project_a.id}" and rec.month == 3).amount,
            300.0,
            places=2,
        )

    def test_matrix_entry_write_recomputes_timesheets_and_reports(self):
        year = fields.Date.context_today(self).year + 1
        self.assignment.write({"max_monthly_wage_hm": 1000.0})
        matrix = self.env["tenenet.project.timesheet.matrix"]._ensure_for_assignment_years(
            self.assignment,
            [year],
        )
        matrix_line = matrix.line_ids.filtered(lambda line: line.hour_type == "pp")[:1]
        march_entry = matrix_line.entry_ids.filtered(lambda entry: entry.period == fields.Date.to_date(f"{year}-03-01"))[:1]

        march_entry.write({"hours": 150.0})

        timesheet = self.env["tenenet.project.timesheet"].search([
            ("assignment_id", "=", self.assignment.id),
            ("period", "=", f"{year}-03-01"),
        ], limit=1)
        wage_expense = self.env["tenenet.internal.expense"].search([
            ("source_assignment_id", "=", self.assignment.id),
            ("period", "=", f"{year}-03-01"),
            ("category", "=", "wage"),
        ], limit=1)

        self.assertEqual(timesheet.hours_pp, 150.0)
        self.assertAlmostEqual(timesheet.total_labor_cost, 2043.0, places=2)
        self.assertAlmostEqual(wage_expense.cost_ccp, 681.0, places=2)

        cashflow_salary = self._column_map(self._find_named_line(self._get_lines(year), "Mzdy"))
        allocation_ccp = self._column_map(self._find_allocation_line(self._get_allocation_lines(year), "CCP"))
        allocation_internal_wage = self._column_map(
            self._find_allocation_line(self._get_allocation_lines(year), "Interné náklady - mzda (CCP)")
        )

        self.assertAlmostEqual(cashflow_salary["month_03"], -2043.0, places=2)
        self.assertAlmostEqual(allocation_ccp["month_03"], 2043.0, places=2)
        self.assertAlmostEqual(allocation_internal_wage["month_03"], 681.0, places=2)

    def test_allocation_report_shows_travel_and_training_internal_lines_as_placeholders(self):
        year = fields.Date.context_today(self).year + 1

        travel_columns = self._column_map(self._find_allocation_line(self._get_allocation_lines(year), "Cestovné náhrady"))
        training_columns = self._column_map(self._find_allocation_line(self._get_allocation_lines(year), "Školenie"))

        self.assertAlmostEqual(travel_columns["year_total"], 0.0, places=2)
        self.assertAlmostEqual(training_columns["year_total"], 0.0, places=2)

    def test_allocation_report_uses_internal_expense_amounts_for_travel_and_training(self):
        year = fields.Date.context_today(self).year + 1
        travel_type = self.env["tenenet.expense.type.config"].create({"name": "Cestovné náhrady"})
        training_type = self.env["tenenet.expense.type.config"].create({"name": "Školenie"})

        self.env["tenenet.internal.expense"].create({
            "employee_id": self.employee.id,
            "period": f"{year}-03-01",
            "category": "expense",
            "source_project_id": self.project_a.id,
            "expense_type_config_id": travel_type.id,
            "expense_amount": 45.0,
        })
        self.env["tenenet.internal.expense"].create({
            "employee_id": self.employee.id,
            "period": f"{year}-04-01",
            "category": "expense",
            "source_project_id": self.project_a.id,
            "expense_type_config_id": training_type.id,
            "expense_amount": 70.0,
        })

        lines = self._get_allocation_lines(year)
        travel_columns = self._column_map(self._find_allocation_line(lines, "Cestovné náhrady"))
        training_columns = self._column_map(self._find_allocation_line(lines, "Školenie"))

        self.assertAlmostEqual(travel_columns["month_03"], 45.0, places=2)
        self.assertAlmostEqual(travel_columns["year_total"], 45.0, places=2)
        self.assertAlmostEqual(training_columns["month_04"], 70.0, places=2)
        self.assertAlmostEqual(training_columns["year_total"], 70.0, places=2)

    def test_salary_row_ignores_stale_override_values(self):
        year = fields.Date.context_today(self).year + 1
        self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment.id,
            "period": f"{year}-04-01",
            "hours_pp": 100.0,
        })
        self.env["tenenet.cashflow.global.override"].create({
            "period": f"{year}-04-01",
            "row_key": "salary:mzdy",
            "row_label": "Mzdy",
            "row_type": "salary",
            "amount": 0.0,
        })

        lines = self._get_lines(year)
        salary_columns = self._column_map(self._find_named_line(lines, "Mzdy"))

        self.assertAlmostEqual(salary_columns["month_04"], -2000.0, places=2)

    def test_residual_wage_hits_cashflow_salary_and_allocation_internal_wage(self):
        year = fields.Date.context_today(self).year + 1
        self.employee.write({"monthly_gross_salary_target": 150.0})
        self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment.id,
            "period": f"{year}-03-01",
            "hours_pp": 10.0,
        })

        residual = self.env["tenenet.internal.expense"].search([
            ("employee_id", "=", self.employee.id),
            ("period", "=", f"{year}-03-01"),
            ("category", "=", "residual_wage"),
        ], limit=1)

        self.assertTrue(residual)
        self.assertTrue(residual.source_project_id.is_tenenet_internal)
        self.assertAlmostEqual(residual.cost_hm, 50.0, places=2)
        self.assertAlmostEqual(residual.cost_ccp, 68.1, places=2)

        cashflow_salary = self._column_map(self._find_named_line(self._get_lines(year), "Mzdy"))
        allocation_ccp = self._column_map(self._find_allocation_line(self._get_allocation_lines(year), "CCP"))
        allocation_internal_wage = self._column_map(
            self._find_allocation_line(self._get_allocation_lines(year), "Interné náklady - mzda (CCP)")
        )

        self.assertAlmostEqual(cashflow_salary["month_03"], -204.3, places=2)
        self.assertAlmostEqual(allocation_ccp["month_03"], 136.2, places=2)
        self.assertAlmostEqual(allocation_internal_wage["month_03"], 68.1, places=2)

    def test_income_override_rebalances_last_active_month_to_project_total(self):
        selected_year = fields.Date.context_today(self).year + 1
        self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": f"{selected_year}-03-01",
            "amount": 1200.0,
        })

        override_model = self.env["tenenet.cashflow.global.override"].with_context(grid_anchor=f"{selected_year}-01-01")
        override_model.action_prepare_grid_year()

        march_row = self.env["tenenet.cashflow.global.override"].search([
            ("year", "=", selected_year),
            ("row_key", "=", f"income:{self.project_a.id}"),
            ("month", "=", 3),
        ], limit=1)
        december_row = self.env["tenenet.cashflow.global.override"].search([
            ("year", "=", selected_year),
            ("row_key", "=", f"income:{self.project_a.id}"),
            ("month", "=", 12),
        ], limit=1)

        march_row.write({"amount": 350.0})

        income_rows = self.env["tenenet.cashflow.global.override"].search([
            ("year", "=", selected_year),
            ("row_key", "=", f"income:{self.project_a.id}"),
        ])
        self.assertAlmostEqual(march_row.amount, 350.0, places=2)
        self.assertAlmostEqual(december_row.amount, 50.0, places=2)
        self.assertAlmostEqual(sum(income_rows.mapped("amount")), 1200.0, places=2)

    def test_deleted_project_cashflow_disappears_from_report(self):
        selected_year = fields.Date.context_today(self).year + 1
        receipt = self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": f"{selected_year}-03-01",
            "amount": 1200.0,
        })

        self.env["tenenet.cashflow.global.override"].with_context(
            grid_anchor=f"{selected_year}-01-01"
        ).action_prepare_grid_year()
        receipt.cashflow_ids.unlink()

        lines = self._get_lines(selected_year)
        self.assertFalse(any(self._column_map(line).get("project_label") == "Projekt A" for line in lines))
        self.assertAlmostEqual(self._column_map(self._find_named_line(lines, "Cash-IN"))["year_total"], 0.0, places=2)

    def test_deleted_project_cashflow_removes_corresponding_override(self):
        selected_year = fields.Date.context_today(self).year + 1
        receipt = self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": f"{selected_year}-03-01",
            "amount": 1200.0,
        })
        override_model = self.env["tenenet.cashflow.global.override"].with_context(grid_anchor=f"{selected_year}-01-01")
        override_model.action_prepare_grid_year()

        receipt.cashflow_ids.unlink()

        overrides = self.env["tenenet.cashflow.global.override"].search([
            ("year", "=", selected_year),
            ("row_key", "=", f"income:{self.project_a.id}"),
        ])
        self.assertFalse(overrides)

    def test_salary_and_project_expense_rows_feed_cash_out_and_balance(self):
        selected_year = fields.Date.context_today(self).year + 1
        self.env["tenenet.project.receipt"].create({
            "project_id": self.project_a.id,
            "date_received": f"{selected_year}-01-01",
            "amount": 1200.0,
        })
        self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment.id,
            "period": f"{selected_year}-01-01",
            "hours_pp": 10.0,
        })
        self.env["tenenet.internal.expense"].create({
            "employee_id": self.employee.id,
            "period": f"{selected_year}-01-01",
            "category": "leave",
            "hours": 5.0,
            "wage_hm": 10.0,
        })
        self.env["tenenet.project.expense"].create({
            "project_id": self.project_a.id,
            "allowed_type_id": self.env["tenenet.project.allowed.expense.type"].create({
                "project_id": self.project_a.id,
                "name": "Cesty",
                "max_amount": 0.0,
            }).id,
            "date": f"{selected_year}-01-15",
            "amount": 50.0,
            "description": "Cesta",
        })
        self.env["tenenet.internal.expense"].create({
            "employee_id": self.employee.id,
            "period": f"{selected_year}-01-01",
            "category": "expense",
            "source_project_id": self.project_a.id,
            "expense_amount": 30.0,
        })

        lines = self._get_lines(selected_year)
        mzdy_line = self._find_named_line(lines, "Mzdy")
        expense_line = self._find_expense_line(lines, "Projektove naklady - Projekt A")
        cash_out_line = self._find_named_line(lines, "Cash-OUT")
        balance_line = self._find_named_line(lines, "Balance per actual month")

        mzdy_columns = self._column_map(mzdy_line)
        expense_columns = self._column_map(expense_line)
        cash_out_columns = self._column_map(cash_out_line)
        balance_columns = self._column_map(balance_line)

        self.assertAlmostEqual(mzdy_columns["month_01"], -250.0, places=2)
        self.assertAlmostEqual(expense_columns["month_01"], -80.0, places=2)
        self.assertAlmostEqual(cash_out_columns["month_01"], -330.0, places=2)
        self.assertAlmostEqual(balance_columns["month_01"], -230.0, places=2)
