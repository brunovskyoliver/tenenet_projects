from odoo import fields
from odoo import Command
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
        employee = self.env["hr.employee"].create({"name": "Payroll Quick Employee"})
        self.env["tenenet.project.assignment"].create({
            "employee_id": employee.id,
            "project_id": service_project.id,
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
            [employee.id],
        )
        budget_line = service_project.budget_line_ids.filtered(lambda line: line.service_income_type == "sales_individual")

        self.assertEqual(len(budget_line), 1)
        self.assertTrue(budget_line.can_cover_payroll)
        self.assertEqual(budget_line.payroll_employee_ids, employee)

    def test_budget_add_action_data_contains_assigned_payroll_employees(self):
        employee = self.env["hr.employee"].create({"name": "Modal Payroll Employee"})
        archived_employee = self.env["hr.employee"].create({"name": "Archived Payroll Employee", "active": False})
        self.env["tenenet.project.assignment"].create({
            "employee_id": employee.id,
            "project_id": self.project.id,
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": archived_employee.id,
            "project_id": self.project.id,
        })

        data = self.project.get_budget_add_action_data()

        self.assertIn({"id": employee.id, "label": employee.display_name}, data["payroll_employee_options"])
        self.assertNotIn(
            {"id": archived_employee.id, "label": archived_employee.display_name},
            data["payroll_employee_options"],
        )

    def test_quick_add_empty_payroll_employees_keeps_all_assigned_eligible(self):
        year = fields.Date.context_today(self).year
        service_project = self.env["tenenet.project"].create({
            "name": "Service Project All Payroll",
            "project_type": "sluzby",
            "program_ids": [Command.set(self.program.ids)],
        })
        employee_a = self.env["hr.employee"].create({"name": "Payroll All A"})
        employee_b = self.env["hr.employee"].create({"name": "Payroll All B"})
        self.env["tenenet.project.assignment"].create({
            "employee_id": employee_a.id,
            "project_id": service_project.id,
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": employee_b.id,
            "project_id": service_project.id,
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
            "Servis bez výberu",
            False,
            "sales_individual",
            True,
            [],
        )
        budget_line = service_project.budget_line_ids.filtered(lambda line: line.service_income_type == "sales_individual")

        self.assertFalse(budget_line.payroll_employee_ids)
        self.assertEqual(budget_line._get_payroll_eligible_employees(f"{year}-03-01"), employee_a | employee_b)

    def test_quick_add_payroll_employees_work_for_any_other_service_income_type(self):
        year = fields.Date.context_today(self).year
        service_project = self.env["tenenet.project"].create({
            "name": "Service Project Invoice Payroll",
            "project_type": "sluzby",
            "program_ids": [Command.set(self.program.ids)],
        })
        employee = self.env["hr.employee"].create({"name": "Invoice Payroll Employee"})
        self.env["tenenet.project.assignment"].create({
            "employee_id": employee.id,
            "project_id": service_project.id,
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
            "Fakturačné krytie",
            False,
            "sales_invoice",
            True,
            [employee.id],
        )
        budget_line = service_project.budget_line_ids.filtered(lambda line: line.service_income_type == "sales_invoice")

        self.assertEqual(budget_line.payroll_employee_ids, employee)

    def test_quick_add_payroll_employees_work_for_generic_other_category(self):
        year = fields.Date.context_today(self).year
        employee = self.env["hr.employee"].create({"name": "Generic Other Payroll Employee"})
        self.env["tenenet.project.assignment"].create({
            "employee_id": employee.id,
            "project_id": self.project.id,
        })
        self.env["tenenet.project.receipt"].create({
            "project_id": self.project.id,
            "date_received": f"{year}-03-01",
            "amount": 1000.0,
        })

        self.project.action_create_budget_line_from_quick_add(
            "other",
            250.0,
            25.0,
            "Bežné iné krytie",
            self.expense_type.id,
            False,
            True,
            [employee.id],
        )
        budget_line = self.project.budget_line_ids.filtered(lambda line: line.expense_type_config_id == self.expense_type)

        self.assertTrue(budget_line.can_cover_payroll)
        self.assertEqual(budget_line.payroll_employee_ids, employee)

    def test_payroll_employee_must_belong_to_same_project(self):
        service_project = self.env["tenenet.project"].create({
            "name": "Service Project Payroll",
            "project_type": "sluzby",
            "program_ids": [Command.set(self.program.ids)],
        })
        employee = self.env["hr.employee"].create({"name": "Payroll Employee"})
        outsider = self.env["hr.employee"].create({"name": "Outsider"})
        self.env["tenenet.project.assignment"].create({
            "employee_id": employee.id,
            "project_id": service_project.id,
        })

        with self.assertRaises(ValidationError):
            self.env["tenenet.project.budget.line"].create({
                "project_id": service_project.id,
                "year": 2027,
                "budget_type": "other",
                "program_id": self.program.id,
                "name": "Payroll line",
                "amount": 300.0,
                "service_income_type": "sales_individual",
                "can_cover_payroll": True,
                "payroll_employee_ids": [Command.set([employee.id, outsider.id])],
            })

    def test_payroll_employee_eligibility_uses_active_assignment_scope(self):
        service_project = self.env["tenenet.project"].create({
            "name": "Scoped Service Project",
            "project_type": "sluzby",
            "program_ids": [Command.set(self.program.ids)],
        })
        employee = self.env["hr.employee"].create({"name": "Scoped Employee"})
        employee_late = self.env["hr.employee"].create({"name": "Late Employee"})
        self.env["tenenet.project.assignment"].create({
            "employee_id": employee.id,
            "project_id": service_project.id,
            "date_start": "2027-01-01",
            "date_end": "2027-12-31",
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": employee_late.id,
            "project_id": service_project.id,
            "date_start": "2027-06-01",
            "date_end": "2027-12-31",
        })
        budget_line = self.env["tenenet.project.budget.line"].create({
            "project_id": service_project.id,
            "year": 2027,
            "budget_type": "other",
            "program_id": self.program.id,
            "name": "Payroll line",
            "amount": 300.0,
            "service_income_type": "sales_individual",
            "can_cover_payroll": True,
            "payroll_employee_ids": [Command.set([employee.id, employee_late.id])],
        })

        eligible_jan = budget_line._get_payroll_eligible_employees("2027-01-01")
        eligible_jul = budget_line._get_payroll_eligible_employees("2027-07-01")

        self.assertEqual(eligible_jan, employee)
        self.assertEqual(eligible_jul, employee | employee_late)

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
