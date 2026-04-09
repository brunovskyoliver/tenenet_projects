from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetBudgetLinePlanner(TransactionCase):
    def setUp(self):
        super().setUp()
        self.admin_program = self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1)
        self.program = self.env["tenenet.program"].create({"name": "Budget Program", "code": "BDG"})
        self.project = self.env["tenenet.project"].create({
            "name": "Budget Planner Project",
            "program_ids": [(6, 0, self.program.ids)],
            "reporting_program_id": self.program.id,
        })

    def test_pausal_budget_line_requires_admin_program(self):
        with self.assertRaises(ValidationError):
            self.env["tenenet.project.budget.line"].create({
                "project_id": self.project.id,
                "year": 2027,
                "budget_type": "pausal",
                "program_id": self.program.id,
                "name": "Paušál",
                "amount": 100.0,
            })

    def test_budget_line_planner_action_opens_modal_form(self):
        budget_line = self.env["tenenet.project.budget.line"].create({
            "project_id": self.project.id,
            "year": 2027,
            "budget_type": "labor",
            "program_id": self.program.id,
            "name": "Mzdový príjem",
            "amount": 600.0,
        })

        action = budget_line.action_open_planner()

        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "tenenet_budget_line_planner_action")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["params"]["budget_line_id"], budget_line.id)

    def test_budget_line_can_store_explicit_month_amounts(self):
        budget_line = self.env["tenenet.project.budget.line"].create({
            "project_id": self.project.id,
            "year": 2027,
            "budget_type": "labor",
            "program_id": self.program.id,
            "name": "Mzdový príjem",
            "amount": 1000.0,
        })

        budget_line.set_month_amounts({
            "2": 300.0,
            "3": 200.0,
        })
        budget_line.invalidate_recordset(["budget_month_ids", "has_explicit_month_plan"])
        payload = budget_line.get_planner_data()

        self.assertTrue(budget_line.has_explicit_month_plan)
        self.assertEqual(sorted(budget_line.budget_month_ids.mapped("month")), [2, 3])
        self.assertEqual(payload["months"]["2"], 300.0)
        self.assertEqual(payload["months"]["3"], 200.0)
        self.assertEqual(payload["months"]["4"], 0.0)

    def test_budget_line_rejects_explicit_month_amounts_above_total(self):
        budget_line = self.env["tenenet.project.budget.line"].create({
            "project_id": self.project.id,
            "year": 2027,
            "budget_type": "other",
            "program_id": self.program.id,
            "name": "Iný príjem",
            "amount": 1000.0,
        })

        with self.assertRaises(ValidationError):
            budget_line.set_month_amounts({
                "1": 800.0,
                "2": 300.0,
            })

    def test_budget_line_uses_fallback_allocation_until_explicit_plan_exists(self):
        self.env["tenenet.project.receipt"].create({
            "project_id": self.project.id,
            "date_received": "2027-03-01",
            "amount": 1200.0,
        })
        budget_line = self.env["tenenet.project.budget.line"].create({
            "project_id": self.project.id,
            "year": 2027,
            "budget_type": "labor",
            "program_id": self.program.id,
            "name": "Mzdový príjem",
            "amount": 120.0,
        })

        payload = budget_line.get_planner_data()

        self.assertFalse(payload["has_explicit_month_plan"])
        self.assertGreater(payload["months"]["3"], 0.0)
