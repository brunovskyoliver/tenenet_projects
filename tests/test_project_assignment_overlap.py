from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetProjectAssignmentOverlap(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({"name": "Overlap Employee"})
        self.project = self.env["tenenet.project"].create({"name": "Overlap Project"})

    def _vals(self, **overrides):
        vals = {
            "employee_id": self.employee.id,
            "project_id": self.project.id,
            "allocation_ratio": 50.0,
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        }
        vals.update(overrides)
        return vals

    def test_historical_versions_can_have_different_rates(self):
        first = self.env["tenenet.project.assignment"].create(
            self._vals(date_start="2026-01-01", date_end="2026-03-31", wage_hm=10.0)
        )
        second = self.env["tenenet.project.assignment"].create(
            self._vals(date_start="2026-04-01", date_end="2026-06-30", wage_hm=12.0)
        )
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.assertNotEqual(first.wage_hm, second.wage_hm)

    def test_open_ended_assignment_allows_overlap(self):
        first = self.env["tenenet.project.assignment"].create(self._vals(date_start="2026-01-01"))
        second = self.env["tenenet.project.assignment"].create(
            self._vals(date_start="2026-05-01", date_end="2026-12-31")
        )
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
