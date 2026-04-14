from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetBudgetLinePlanner(TransactionCase):
    def setUp(self):
        super().setUp()
        self.admin_program = self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1)
        self.program = self.env["tenenet.program"].create({"name": "Budget Program", "code": "BDG"})
        self.expense_type = self.env["tenenet.expense.type.config"].create({"name": "Cestovné"})
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

    def test_project_budget_add_action_opens_custom_modal(self):
        action = self.project.action_open_budget_wizard()

        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "tenenet_budget_add_action")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["params"]["project_id"], self.project.id)

    def test_project_budget_add_flow_creates_line_and_opens_planner(self):
        year = fields.Date.context_today(self).year
        self.env["tenenet.project.receipt"].create({
            "project_id": self.project.id,
            "date_received": f"{year}-03-01",
            "amount": 1000.0,
        })

        action = self.project.action_create_budget_line_from_quick_add(
            "labor",
            200.0,
            20.0,
            "Poznámka",
        )
        budget_line = self.project.budget_line_ids.filtered(lambda line: line.amount == 200.0)

        self.assertEqual(len(budget_line), 1)
        self.assertEqual(budget_line.program_id, self.program)
        self.assertEqual(budget_line.note, "Poznámka")
        self.assertEqual(action["tag"], "tenenet_budget_line_planner_action")
        self.assertEqual(action["params"]["budget_line_id"], budget_line.id)

    def test_quick_add_other_requires_expense_category(self):
        year = fields.Date.context_today(self).year
        self.env["tenenet.project.receipt"].create({
            "project_id": self.project.id,
            "date_received": f"{year}-03-01",
            "amount": 1000.0,
        })

        with self.assertRaises(ValidationError):
            self.project.action_create_budget_line_from_quick_add("other", 200.0, 20.0)

    def test_service_project_budget_line_accepts_service_income_and_payroll_flag(self):
        year = fields.Date.context_today(self).year
        service_project = self.env["tenenet.project"].create({
            "name": "Service Project",
            "project_type": "sluzby",
            "program_ids": [(4, self.program.id)],
        })
        self.env["tenenet.project.receipt"].create({
            "project_id": service_project.id,
            "date_received": f"{year}-03-01",
            "amount": 1000.0,
        })

        service_project.action_create_budget_line_from_quick_add(
            "other",
            250.0,
            25.0,
            "Servis",
            False,
            "sales_individual",
            True,
        )
        budget_line = service_project.budget_line_ids.filtered(lambda line: line.service_income_type == "sales_individual")

        self.assertEqual(len(budget_line), 1)
        self.assertTrue(budget_line.can_cover_payroll)

    def test_generic_other_budget_line_uses_expense_category_label(self):
        budget_line = self.env["tenenet.project.budget.line"].create({
            "project_id": self.project.id,
            "year": 2027,
            "budget_type": "other",
            "program_id": self.program.id,
            "name": "Iné",
            "amount": 300.0,
            "expense_type_config_id": self.expense_type.id,
        })

        self.assertEqual(budget_line.detail_label, "Cestovné")

    def test_budget_line_delete_action_removes_record(self):
        budget_line = self.env["tenenet.project.budget.line"].create({
            "project_id": self.project.id,
            "year": 2027,
            "budget_type": "labor",
            "program_id": self.program.id,
            "name": "Mazaná položka",
            "amount": 150.0,
        })

        action = budget_line.action_delete_with_reload()

        self.assertFalse(budget_line.exists())
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "soft_reload")

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
            "expense_type_config_id": self.expense_type.id,
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
