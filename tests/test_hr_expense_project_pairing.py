from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHrExpenseProjectPairing(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({"name": "Expense Employee"})
        self.other_employee = self.env["hr.employee"].create({"name": "Other Employee"})
        self.expense_product = self.env["product.product"].create({
            "name": "Cestovné HR",
            "type": "service",
            "can_be_expensed": True,
        })
        self.expense_type = self.env["tenenet.expense.type.config"].create({
            "name": "Cestovné",
            "expense_category_line_ids": [(0, 0, {
                "product_id": self.expense_product.id,
            })],
        })
        self.allowed_project = self.env["tenenet.project"].create({
            "name": "Projekt Expense",
        })
        self.allowed_project.allowed_expense_type_ids = [(0, 0, {
            "config_id": self.expense_type.id,
            "name": self.expense_type.name,
            "max_amount": 100.0,
        })]
        self.disallowed_project = self.env["tenenet.project"].create({
            "name": "Projekt Bez Typu",
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.allowed_project.id,
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": self.other_employee.id,
            "project_id": self.disallowed_project.id,
        })

    def _create_expense(self, amount, project):
        return self.env["hr.expense"].create({
            "name": "Test expense",
            "employee_id": self.employee.id,
            "total_amount_currency": amount,
            "tenenet_project_id": project.id,
            "tenenet_expense_type_config_id": self.expense_type.id,
        })

    def test_available_projects_are_limited_to_employee_context(self):
        expense = self.env["hr.expense"].new({
            "employee_id": self.employee.id,
        })
        available_ids = set(expense.tenenet_available_project_ids.ids)
        self.assertIn(self.allowed_project.id, available_ids)
        self.assertNotIn(self.disallowed_project.id, available_ids)

    def test_allowed_expense_syncs_fully_to_project(self):
        expense = self._create_expense(60.0, self.allowed_project)

        self.assertEqual(expense.product_id, self.expense_product)
        self.assertEqual(expense.tenenet_project_amount, 60.0)
        self.assertEqual(expense.tenenet_internal_amount, 0.0)
        self.assertEqual(len(expense.tenenet_project_expense_ids), 1)
        self.assertFalse(expense.tenenet_internal_expense_ids)
        self.assertEqual(expense.tenenet_project_expense_ids.amount, 60.0)

    def test_over_limit_expense_is_split_between_project_and_internal(self):
        first_expense = self._create_expense(60.0, self.allowed_project)
        second_expense = self._create_expense(80.0, self.allowed_project)

        self.assertEqual(first_expense.tenenet_project_amount, 60.0)
        self.assertEqual(second_expense.tenenet_project_amount, 40.0)
        self.assertEqual(second_expense.tenenet_internal_amount, 40.0)
        self.assertEqual(second_expense.tenenet_project_expense_ids.amount, 40.0)
        self.assertEqual(second_expense.tenenet_internal_expense_ids.expense_amount, 40.0)
