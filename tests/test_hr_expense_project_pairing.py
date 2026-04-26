from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHrExpenseProjectPairing(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({"name": "Expense Employee", "work_ratio": 200.0})
        self.other_employee = self.env["hr.employee"].create({"name": "Other Employee"})
        self.expense_product = self.env["product.product"].create({
            "name": "Cestovné HR",
            "type": "service",
            "can_be_expensed": True,
        })
        self.expense_type = self.env["tenenet.expense.type.config"].create({
            "name": "Cestovné",
            "hr_expense_product_id": self.expense_product.id,
        })
        self.operating_product = self.env["product.product"].create({
            "name": "Prevádzka HR",
            "type": "service",
            "can_be_expensed": True,
        })
        self.operating_type = self.env["tenenet.expense.type.config"].create({
            "name": "Nájom",
            "tenenet_usage": "operating",
            "hr_expense_product_id": self.operating_product.id,
            "cashflow_row_key": "workbook:expense:prevadzkove-n-najom",
            "cashflow_row_label": "Prevadzkove N - najom",
            "admin_pl_row_key": "operating:rent",
            "admin_pl_row_label": "Nájom",
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

    def test_adding_allowed_type_resyncs_existing_hr_expense(self):
        late_project = self.env["tenenet.project"].create({"name": "Projekt Neskorý Typ"})
        self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": late_project.id,
        })
        expense = self._create_expense(60.0, late_project)

        self.assertFalse(expense.tenenet_project_expense_ids)
        self.assertEqual(expense.tenenet_internal_amount, 60.0)
        self.assertEqual(expense.tenenet_internal_expense_ids.expense_amount, 60.0)

        late_project.allowed_expense_type_ids = [(0, 0, {
            "config_id": self.expense_type.id,
            "name": self.expense_type.name,
            "max_amount": 100.0,
        })]
        expense.invalidate_recordset()

        self.assertEqual(expense.tenenet_project_amount, 60.0)
        self.assertEqual(expense.tenenet_internal_amount, 0.0)
        self.assertEqual(len(expense.tenenet_project_expense_ids), 1)
        self.assertFalse(expense.tenenet_internal_expense_ids)

    def test_expense_can_create_missing_allowed_type_from_form_shortcut(self):
        late_project = self.env["tenenet.project"].create({"name": "Projekt Skratka"})
        self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": late_project.id,
        })

        expense = self.env["hr.expense"].create({
            "name": "Shortcut expense",
            "employee_id": self.employee.id,
            "total_amount_currency": 60.0,
            "tenenet_project_id": late_project.id,
            "tenenet_expense_type_config_id": self.expense_type.id,
            "tenenet_add_allowed_type": True,
            "tenenet_allowed_type_limit": 100.0,
        })
        allowed_type = late_project.allowed_expense_type_ids.filtered(
            lambda rec: rec.config_id == self.expense_type
        )

        self.assertEqual(len(allowed_type), 1)
        self.assertEqual(allowed_type.name, self.expense_type.name)
        self.assertEqual(allowed_type.description, self.expense_type.description)
        self.assertEqual(allowed_type.max_amount, 100.0)
        self.assertEqual(expense.tenenet_project_amount, 60.0)
        self.assertEqual(expense.tenenet_internal_amount, 0.0)
        self.assertEqual(len(expense.tenenet_project_expense_ids), 1)

    def test_expense_shortcut_does_not_duplicate_existing_allowed_type(self):
        expense = self.env["hr.expense"].create({
            "name": "Duplicate shortcut expense",
            "employee_id": self.employee.id,
            "total_amount_currency": 40.0,
            "tenenet_project_id": self.allowed_project.id,
            "tenenet_expense_type_config_id": self.expense_type.id,
            "tenenet_add_allowed_type": True,
            "tenenet_allowed_type_limit": 999.0,
        })
        allowed_types = self.allowed_project.allowed_expense_type_ids.filtered(
            lambda rec: rec.config_id == self.expense_type
        )

        self.assertEqual(len(allowed_types), 1)
        self.assertEqual(allowed_types.max_amount, 100.0)
        self.assertEqual(expense.tenenet_project_amount, 40.0)
        self.assertEqual(expense.tenenet_internal_amount, 0.0)

    def test_operating_expense_without_project_syncs_to_internal_expense(self):
        expense = self.env["hr.expense"].create({
            "name": "Operating rent",
            "employee_id": self.employee.id,
            "total_amount_currency": 80.0,
            "tenenet_cost_flow": "operating",
            "tenenet_expense_type_config_id": self.operating_type.id,
        })

        self.assertEqual(expense.product_id, self.operating_product)
        self.assertFalse(expense.tenenet_project_id)
        self.assertEqual(expense.tenenet_project_amount, 0.0)
        self.assertEqual(expense.tenenet_internal_amount, 80.0)
        self.assertFalse(expense.tenenet_project_expense_ids)
        self.assertEqual(len(expense.tenenet_internal_expense_ids), 1)
        self.assertFalse(expense.tenenet_internal_expense_ids.source_project_id)
        self.assertEqual(expense.tenenet_internal_expense_ids.expense_amount, 80.0)
