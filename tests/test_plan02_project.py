from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan02Project(TransactionCase):
    def setUp(self):
        super().setUp()
        self.donor_partner = self.env["res.partner"].create(
            {
                "name": "Donor Kontakt",
                "email": "donor@test.sk",
                "phone": "+421900111111",
            }
        )
        self.project_partner = self.env["res.partner"].create(
            {
                "name": "Partner Projektu",
                "email": "partner@test.sk",
                "phone": "+421900222222",
            }
        )
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
                "partner_id": self.donor_partner.id,
            }
        )
        self.employee = self.env["hr.employee"].create({"name": "Projektový Manažér"})

    def test_project_create_with_relations(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt A",
                "program_ids": [(4, self.program.id)],
                "donor_id": self.donor.id,
                "partner_id": self.project_partner.id,
                "odborny_garant_id": self.employee.id,
                "project_manager_id": self.employee.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "semaphore": "green",
            }
        )

        self.assertIn(self.program, project.program_ids)
        self.assertEqual(project.donor_id, self.donor)
        self.assertEqual(project.odborny_garant_id, self.employee)
        self.assertEqual(project.partner_id, self.project_partner)
        self.assertEqual(project.duration, 12)
        self.assertIn("donor@test.sk", project.donor_contact)
        self.assertIn("partner@test.sk", project.partner_contact)

    def test_project_budget_total_compute(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt B",
                "program_ids": [(4, self.program.id)],
                "donor_id": self.donor.id,
            }
        )

        self.env["tenenet.project.receipt"].create([
            {"project_id": project.id, "date_received": "2024-03-01", "amount": 500.0},
            {"project_id": project.id, "date_received": "2025-03-01", "amount": 600.0},
            {"project_id": project.id, "date_received": "2026-03-01", "amount": 700.0},
        ])
        self.assertEqual(project.budget_total, 1800.0)

    def test_project_semaphore_selection(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt D",
                "program_ids": [(4, self.program.id)],
                "donor_id": self.donor.id,
                "semaphore": "yellow",
            }
        )

        self.assertEqual(project.semaphore, "yellow")

    def test_project_active_year_range_from_dates(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt E",
                "program_ids": [(4, self.program.id)],
                "donor_id": self.donor.id,
                "date_start": "2024-02-01",
                "date_end": "2026-11-30",
            }
        )

        self.assertEqual(project.active_year_from, 2024)
        self.assertEqual(project.active_year_to, 2026)
