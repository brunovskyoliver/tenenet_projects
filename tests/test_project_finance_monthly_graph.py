from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged("post_install", "-at_install")
class TestProjectFinanceMonthlyGraph(TransactionCase):
    def setUp(self):
        super().setUp()
        self.current_year = fields.Date.context_today(self).year
        self.program = self.env["tenenet.program"].create({
            "name": "Program Financie",
            "code": "FIN_GRAPH",
        })
        self.project = self.env["tenenet.project"].create({
            "name": "Projekt Graf Financii",
            "program_ids": [(6, 0, self.program.ids)],
        })
        self.employee = self.env["hr.employee"].create({"name": "Graf Zamestnanec"})
        self.assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.project.id,
            "wage_hm": 10.0,
            "wage_ccp": 20.0,
        })
        self.allowed_type = self.env["tenenet.project.allowed.expense.type"].create({
            "project_id": self.project.id,
            "name": "Cesty",
            "max_amount": 0.0,
        })

    def _line_amount(self, year, month, series):
        line = self.env["tenenet.project.finance.monthly.line"].search([
            ("project_id", "=", self.project.id),
            ("year", "=", year),
            ("month", "=", month),
            ("series", "=", series),
        ], limit=1)
        self.assertTrue(line)
        return line.amount

    def test_rows_cover_whole_year_and_follow_cashflow_override_and_real_spend(self):
        receipt = self.env["tenenet.project.receipt"].create({
            "project_id": self.project.id,
            "date_received": f"{self.current_year}-01-10",
            "amount": 600.0,
        })
        receipt.set_cashflow_month_amounts(self.current_year, {
            1: 100.0,
            2: 200.0,
            3: 300.0,
        })
        self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment.id,
            "period": f"{self.current_year}-03-01",
            "hours_pp": 10.0,
        })
        self.env["tenenet.project.expense"].create({
            "project_id": self.project.id,
            "allowed_type_id": self.allowed_type.id,
            "date": f"{self.current_year}-03-15",
            "amount": 50.0,
            "description": "Cesta",
        })

        override_model = self.env["tenenet.cashflow.global.override"].with_context(
            grid_anchor=f"{self.current_year}-01-01"
        )
        override_model.action_prepare_grid_year()
        override_row = self.env["tenenet.cashflow.global.override"].search([
            ("year", "=", self.current_year),
            ("row_key", "=", f"income:{self.project.id}"),
            ("month", "=", 2),
        ], limit=1)
        override_row.write({"amount": 250.0})

        all_rows = self.env["tenenet.project.finance.monthly.line"].search([
            ("project_id", "=", self.project.id),
            ("year", "=", self.current_year),
        ])
        self.assertEqual(len(all_rows), 24)
        self.assertAlmostEqual(self._line_amount(self.current_year, 1, "predicted_cf"), 100.0, places=2)
        self.assertAlmostEqual(self._line_amount(self.current_year, 2, "predicted_cf"), 250.0, places=2)
        self.assertAlmostEqual(self._line_amount(self.current_year, 3, "predicted_cf"), 300.0, places=2)
        self.assertAlmostEqual(self._line_amount(self.current_year, 3, "real_expense"), 250.0, places=2)
        self.assertAlmostEqual(self._line_amount(self.current_year, 4, "real_expense"), 0.0, places=2)
        chart_data = self.project.get_finance_monthly_comparison_chart_data(self.current_year)
        self.assertEqual(chart_data["year"], self.current_year)
        self.assertEqual(chart_data["series"][0]["values"][1], 200.0)
        self.assertEqual(chart_data["series"][1]["values"][2], 250.0)

    def test_year_switch_shows_selected_year_rows(self):
        next_year = self.current_year + 1
        receipt = self.env["tenenet.project.receipt"].create({
            "project_id": self.project.id,
            "date_received": f"{next_year}-02-01",
            "amount": 400.0,
        })
        receipt.set_cashflow_month_amounts(next_year, {
            2: 150.0,
            3: 250.0,
        })

        self.project.write({"finance_graph_year": next_year})
        self.project.invalidate_recordset(["finance_graph_year", "finance_monthly_comparison_line_ids"])

        self.assertEqual(self.project.finance_graph_year, next_year)
        self.assertEqual(
            set(self.project.finance_monthly_comparison_line_ids.mapped("year")),
            {next_year},
        )
        self.assertAlmostEqual(self._line_amount(next_year, 2, "predicted_cf"), 150.0, places=2)
        self.assertEqual(len(self.project.finance_monthly_comparison_line_ids), 24)

    def test_deleting_sources_resets_month_values_to_zero(self):
        receipt = self.env["tenenet.project.receipt"].create({
            "project_id": self.project.id,
            "date_received": f"{self.current_year}-01-01",
            "amount": 300.0,
        })
        receipt.set_cashflow_month_amounts(self.current_year, {1: 300.0})
        timesheet = self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment.id,
            "period": f"{self.current_year}-01-01",
            "hours_pp": 5.0,
        })
        expense = self.env["tenenet.project.expense"].create({
            "project_id": self.project.id,
            "allowed_type_id": self.allowed_type.id,
            "date": f"{self.current_year}-01-05",
            "amount": 25.0,
            "description": "Cesta",
        })

        self.assertAlmostEqual(self._line_amount(self.current_year, 1, "predicted_cf"), 300.0, places=2)
        self.assertAlmostEqual(self._line_amount(self.current_year, 1, "real_expense"), 125.0, places=2)

        timesheet.unlink()
        expense.unlink()
        receipt.unlink()

        self.assertAlmostEqual(self._line_amount(self.current_year, 1, "predicted_cf"), 0.0, places=2)
        self.assertAlmostEqual(self._line_amount(self.current_year, 1, "real_expense"), 0.0, places=2)

    def test_receipt_cashflow_cannot_start_before_receipt_month(self):
        receipt = self.env["tenenet.project.receipt"].create({
            "project_id": self.project.id,
            "date_received": f"{self.current_year}-02-03",
            "amount": 1200.0,
        })

        self.assertEqual(sorted(receipt.cashflow_ids.mapped("month")), list(range(2, 13)))
        with self.assertRaises(ValidationError):
            receipt.set_cashflow_month_amounts(self.current_year, {
                1: 100.0,
                2: 1100.0,
            })
