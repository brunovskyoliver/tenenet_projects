from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetEmployeeAvailability(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({"name": "Availability Employee"})
        self.project = self.env["tenenet.project"].create({"name": "Availability Project"})
        self.assignment_model = self.env["tenenet.project.assignment"]

    def _create_assignment(self, **overrides):
        vals = {
            "employee_id": self.employee.id,
            "project_id": self.project.id,
            "allocation_ratio": 100.0,
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        }
        vals.update(overrides)
        return self.assignment_model.create(vals)

    def test_employee_without_assignment_is_free(self):
        self.employee.invalidate_recordset()
        self.assertEqual(self.employee.tenenet_availability_state, "free")
        self.assertAlmostEqual(self.employee.tenenet_free_ratio, 100.0, places=2)

    def test_partial_full_and_overbooked_states(self):
        self._create_assignment(allocation_ratio=40.0)
        self.employee.invalidate_recordset()
        self.assertEqual(self.employee.tenenet_availability_state, "partial")
        self.assertAlmostEqual(self.employee.tenenet_free_ratio, 60.0, places=2)

        self.project2 = self.env["tenenet.project"].create({"name": "Availability Project 2"})
        self.assignment_model.create({
            "employee_id": self.employee.id,
            "project_id": self.project2.id,
            "allocation_ratio": 60.0,
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        })
        self.employee.invalidate_recordset()
        self.assertEqual(self.employee.tenenet_availability_state, "full")

        self.project3 = self.env["tenenet.project"].create({"name": "Availability Project 3"})
        self.assignment_model.create({
            "employee_id": self.employee.id,
            "project_id": self.project3.id,
            "allocation_ratio": 10.0,
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        })
        self.employee.invalidate_recordset()
        self.assertEqual(self.employee.tenenet_availability_state, "overbooked")

    def test_finished_and_future_assignments_are_excluded(self):
        self._create_assignment(allocation_ratio=40.0, date_end="2025-01-31")
        self._create_assignment(
            project_id=self.env["tenenet.project"].create({"name": "Future Project"}).id,
            allocation_ratio=25.0,
            date_start="2099-01-01",
        )
        self.employee.invalidate_recordset()
        self.assertEqual(self.employee.tenenet_availability_state, "free")
