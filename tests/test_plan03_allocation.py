from psycopg2 import IntegrityError

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan03Allocation(TransactionCase):
    def setUp(self):
        super().setUp()
        self.program = self.env["tenenet.program"].create(
            {
                "name": "Program Alokácie",
                "code": "PG_ALLOC",
                "headcount": 1.0,
            }
        )
        self.donor = self.env["tenenet.donor"].create(
            {
                "name": "Donor Alokácie",
                "donor_type": "eu",
            }
        )
        self.employee = self.env["hr.employee"].create({"name": "Zamestnanec Alokácie"})
        self.project = self.env["tenenet.project"].create(
            {
                "name": "Projekt Alokácie",
                "program_id": self.program.id,
                "donor_id": self.donor.id,
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
            }
        )

    def test_allocation_hours_total_compute(self):
        allocation = self.env["tenenet.employee.allocation"].create(
            {
                "employee_id": self.employee.id,
                "project_id": self.project.id,
                "period": "2025-01-01",
                "hours_pp": 10.0,
                "hours_np": 5.0,
                "hours_travel": 2.0,
                "hours_training": 3.0,
                "hours_ambulance": 4.0,
                "hours_international": 1.0,
            }
        )

        self.assertEqual(allocation.hours_total, 25.0)

    def test_allocation_total_labor_cost_compute(self):
        allocation = self.env["tenenet.employee.allocation"].create(
            {
                "employee_id": self.employee.id,
                "project_id": self.project.id,
                "period": "2025-02-01",
                "gross_salary": 1500.0,
                "deductions": 550.0,
            }
        )

        self.assertEqual(allocation.total_labor_cost, 2050.0)

    def test_allocation_unique_constraint(self):
        self.env["tenenet.employee.allocation"].create(
            {
                "employee_id": self.employee.id,
                "project_id": self.project.id,
                "period": "2025-03-01",
            }
        )

        with self.cr.savepoint():
            with self.assertRaises(IntegrityError):
                self.env["tenenet.employee.allocation"].create(
                    {
                        "employee_id": self.employee.id,
                        "project_id": self.project.id,
                        "period": "2025-03-01",
                    }
                )

    def test_allocation_cascade_delete_from_project(self):
        allocation = self.env["tenenet.employee.allocation"].create(
            {
                "employee_id": self.employee.id,
                "project_id": self.project.id,
                "period": "2025-04-01",
            }
        )
        allocation_id = allocation.id

        self.project.unlink()

        self.assertFalse(self.env["tenenet.employee.allocation"].browse(allocation_id).exists())
