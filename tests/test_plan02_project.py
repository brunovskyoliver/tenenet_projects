from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan02Project(TransactionCase):
    def setUp(self):
        super().setUp()
        self.program = self.env["tenenet.program"].create(
            {
                "name": "Program Test",
                "code": "PG_TEST",
                "headcount": 1.0,
            }
        )
        self.donor = self.env["tenenet.donor"].create(
            {
                "name": "Donor Test",
                "donor_type": "eu",
            }
        )
        self.employee = self.env["hr.employee"].create({"name": "Projektový Manažér"})

    def test_project_create_with_relations(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt A",
                "code": "PA001",
                "year": 2026,
                "program_id": self.program.id,
                "donor_id": self.donor.id,
                "program_director_id": self.employee.id,
                "project_manager_id": self.employee.id,
                "financial_manager_id": self.employee.id,
                "semaphore": "green",
            }
        )

        self.assertEqual(project.program_id, self.program)
        self.assertEqual(project.donor_id, self.donor)
        self.assertEqual(project.program_director_id, self.employee)

    def test_project_received_total_compute(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt B",
                "program_id": self.program.id,
                "donor_id": self.donor.id,
                "received_2020": 100.0,
                "received_2021": 200.0,
                "received_2022": 300.0,
                "received_2023": 400.0,
                "received_2024": 500.0,
                "received_2025": 600.0,
                "received_2026": 700.0,
            }
        )

        self.assertEqual(project.received_total, 2800.0)

    def test_project_budget_diff_compute(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt C",
                "program_id": self.program.id,
                "donor_id": self.donor.id,
                "amount_contracted": 5000.0,
                "received_2025": 1200.0,
                "received_2026": 800.0,
            }
        )

        self.assertEqual(project.received_total, 2000.0)
        self.assertEqual(project.budget_diff, 3000.0)

    def test_project_semaphore_selection(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt D",
                "program_id": self.program.id,
                "donor_id": self.donor.id,
                "semaphore": "yellow",
            }
        )

        self.assertEqual(project.semaphore, "yellow")
