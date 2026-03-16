from psycopg2 import IntegrityError

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan01(TransactionCase):
    def test_program_unique_code_constraint(self):
        self.env["tenenet.program"].create(
            {
                "name": "Test Program A",
                "code": "TPA",
                "headcount": 1.0,
            }
        )

        with self.assertRaises(IntegrityError):
            self.env["tenenet.program"].create(
                {
                    "name": "Test Program B",
                    "code": "TPA",
                    "headcount": 2.0,
                }
            )

    def test_program_allocation_pct_compute(self):
        p1 = self.env["tenenet.program"].create(
            {
                "name": "Program 1",
                "code": "P1",
                "headcount": 8.0,
            }
        )
        p2 = self.env["tenenet.program"].create(
            {
                "name": "Program 2",
                "code": "P2",
                "headcount": 2.0,
            }
        )

        self.assertAlmostEqual(p1.allocation_pct, 0.8, places=4)
        self.assertAlmostEqual(p2.allocation_pct, 0.2, places=4)

    def test_donor_creation_with_selection(self):
        donor = self.env["tenenet.donor"].create(
            {
                "name": "Test Donor",
                "donor_type": "eu",
            }
        )
        self.assertEqual(donor.donor_type, "eu")

    def test_hr_employee_tenenet_fields(self):
        employee = self.env["hr.employee"].create(
            {
                "name": "Test Zamestnanec",
                "tenenet_number": 123,
                "title_academic": "Mgr.",
                "position": "Sociálny pracovník",
                "work_hours": 8.0,
                "work_ratio": 100.0,
                "hourly_rate": 15.5,
            }
        )

        self.assertEqual(employee.tenenet_number, 123)
        self.assertEqual(employee.title_academic, "Mgr.")
        self.assertEqual(employee.position, "Sociálny pracovník")
