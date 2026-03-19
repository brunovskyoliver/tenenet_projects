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
                "code": "PA001",
                "year": 2026,
                "program_id": self.program.id,
                "donor_id": self.donor.id,
                "partner_id": self.project_partner.id,
                "odborny_garant_id": self.employee.id,
                "project_manager_id": self.employee.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "semaphore": "green",
            }
        )

        self.assertEqual(project.program_id, self.program)
        self.assertEqual(project.donor_id, self.donor)
        self.assertEqual(project.odborny_garant_id, self.employee)
        self.assertEqual(project.partner_id, self.project_partner)
        self.assertEqual(project.duration, 12)
        self.assertIn("donor@test.sk", project.donor_contact)
        self.assertIn("partner@test.sk", project.partner_contact)

    def test_project_received_total_compute(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt B",
                "program_id": self.program.id,
                "donor_id": self.donor.id,
                "date_start": "2024-01-01",
                "date_end": "2026-12-31",
            }
        )

        receipt_by_year = {line.year: line for line in project.receipt_line_ids}
        receipt_by_year[2024].write({"amount": 500.0})
        receipt_by_year[2025].write({"amount": 600.0})
        receipt_by_year[2026].write({"amount": 700.0})
        self.assertEqual(project.received_total, 1800.0)

    def test_project_budget_diff_compute(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt C",
                "program_id": self.program.id,
                "donor_id": self.donor.id,
                "date_start": "2025-01-01",
                "date_end": "2026-12-31",
                "amount_contracted": 5000.0,
            }
        )

        receipt_by_year = {line.year: line for line in project.receipt_line_ids}
        receipt_by_year[2025].write({"amount": 1200.0})
        receipt_by_year[2026].write({"amount": 800.0})
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

    def test_project_receipt_lines_follow_date_range(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt E",
                "program_id": self.program.id,
                "donor_id": self.donor.id,
                "date_start": "2024-02-01",
                "date_end": "2026-11-30",
            }
        )

        self.assertEqual(project.active_year_from, 2024)
        self.assertEqual(project.active_year_to, 2026)
        self.assertEqual(sorted(project.receipt_line_ids.mapped("year")), [2024, 2025, 2026])

        project.write(
            {
                "date_start": "2025-01-01",
                "date_end": "2027-12-31",
            }
        )

        self.assertEqual(sorted(project.receipt_line_ids.mapped("year")), [2025, 2026, 2027])
