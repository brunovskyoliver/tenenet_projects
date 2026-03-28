from psycopg2 import IntegrityError

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan01(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.calendar_6h = cls.env["resource.calendar"].create({
            "name": "Test 6h",
            "hours_per_day": 6.0,
        })

    def test_program_unique_code_constraint(self):
        self.env["tenenet.program"].create(
            {
                "name": "Test Program A",
                "code": "TPA",
                "headcount": 1.0,
            }
        )

        with self.cr.savepoint():
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

        total_headcount = sum(self.env["tenenet.program"].search([]).mapped("headcount"))
        self.assertAlmostEqual(p1.allocation_pct, p1.headcount / total_headcount, places=4)
        self.assertAlmostEqual(p2.allocation_pct, p2.headcount / total_headcount, places=4)

    def test_donor_creation_with_selection(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Test Donor Partner",
                "email": "donor@example.com",
                "phone": "+421900000001",
            }
        )
        donor = self.env["tenenet.donor"].create(
            {
                "name": "Test Donor",
                "donor_type": "eu",
                "partner_id": partner.id,
            }
        )
        self.assertEqual(donor.donor_type, "eu")
        self.assertEqual(donor.partner_id, partner)
        self.assertIn("donor@example.com", donor.contact_info)

    def test_hr_employee_tenenet_fields(self):
        employee = self.env["hr.employee"].create(
            {
                "name": "Test Zamestnanec",
                "tenenet_number": 123,
                "title_academic": "Mgr.",
                "first_name": "Test",
                "last_name": "Zamestnanec",
                "position": "Sociálny pracovník",
                "resource_calendar_id": self.calendar_6h.id,
                "hourly_rate": 15.5,
            }
        )

        self.assertEqual(employee.tenenet_number, 123)
        self.assertEqual(employee.title_academic, "Mgr.")
        self.assertEqual(employee.first_name, "Test")
        self.assertEqual(employee.last_name, "Zamestnanec")
        self.assertEqual(employee.name, "Mgr. Test Zamestnanec")
        self.assertEqual(employee.legal_name, "Test Zamestnanec")
        self.assertEqual(employee.position, "Sociálny pracovník")
        self.assertEqual(employee.position_catalog_id.name, "Sociálny pracovník")
        self.assertEqual(employee.job_id.name, "Sociálny pracovník")
        self.assertAlmostEqual(employee.work_hours, 6.0, places=2)
        self.assertAlmostEqual(employee.work_ratio, 75.0, places=2)
        self.assertAlmostEqual(employee.monthly_capacity_hours, 120.0, places=2)

        employee.write({
            "title_academic": "Bc.",
            "first_name": "Novy",
            "last_name": "Zamestnanec",
        })
        self.assertEqual(employee.name, "Bc. Novy Zamestnanec")
        self.assertEqual(employee.legal_name, "Novy Zamestnanec")

        second_employee = self.env["hr.employee"].create({
            "name": "Druhy Zamestnanec",
            "position": "Sociálny pracovník",
        })
        self.assertEqual(second_employee.position_catalog_id, employee.position_catalog_id)

    def test_program_delete_detaches_linked_projects(self):
        partner = self.env["res.partner"].create({"name": "Donor Partner"})
        donor = self.env["tenenet.donor"].create(
            {
                "name": "Test Donor",
                "donor_type": "eu",
                "partner_id": partner.id,
            }
        )
        program = self.env["tenenet.program"].create(
            {
                "name": "Program With Project",
                "code": "PWP",
                "headcount": 1.0,
            }
        )
        project = self.env["tenenet.project"].create(
            {
                "name": "Linked Project",
                "program_ids": [(4, program.id)],
                "donor_id": donor.id,
            }
        )

        program.unlink()

        self.assertFalse(project.exists().program_ids)
