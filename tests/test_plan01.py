from psycopg2 import IntegrityError

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan01(TransactionCase):
    def test_program_unique_code_constraint(self):
        self.env["tenenet.program"].create(
            {
                "name": "Test Program A",
                "code": "TPA",
            }
        )

        with self.cr.savepoint():
            with self.assertRaises(IntegrityError):
                self.env["tenenet.program"].create(
                    {
                        "name": "Test Program B",
                        "code": "TPA",
                    }
                )

    def test_program_allocation_pct_compute(self):
        p1 = self.env["tenenet.program"].create(
            {
                "name": "Program 1",
                "code": "P1",
            }
        )
        p2 = self.env["tenenet.program"].create(
            {
                "name": "Program 2",
                "code": "P2",
            }
        )
        employee_a = self.env["hr.employee"].create({"name": "Employee A"})
        employee_b = self.env["hr.employee"].create({"name": "Employee B"})
        employee_c = self.env["hr.employee"].create({"name": "Employee C"})
        employee_d = self.env["hr.employee"].create({"name": "Employee D"})
        project_1 = self.env["tenenet.project"].create({"name": "Project 1", "program_ids": [(4, p1.id)]})
        project_2 = self.env["tenenet.project"].create({"name": "Project 2", "program_ids": [(4, p1.id)]})
        project_3 = self.env["tenenet.project"].create({"name": "Project 3", "program_ids": [(4, p2.id)]})
        self.env["tenenet.project.assignment"].create([
            {"employee_id": employee_a.id, "project_id": project_1.id, "program_id": p1.id},
            {"employee_id": employee_b.id, "project_id": project_1.id, "program_id": p1.id},
            {"employee_id": employee_c.id, "project_id": project_2.id, "program_id": p1.id},
            {"employee_id": employee_d.id, "project_id": project_3.id, "program_id": p2.id},
        ])

        total_headcount = sum(self.env["tenenet.program"].search([]).mapped("headcount"))
        self.assertAlmostEqual(p1.allocation_pct, p1.headcount / total_headcount, places=4)
        self.assertAlmostEqual(p2.allocation_pct, p2.headcount / total_headcount, places=4)
        self.assertEqual(p1.headcount, 3.0)
        self.assertEqual(p2.headcount, 1.0)

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
                "work_ratio": 75.0,
                "hourly_rate": 15.5,
            }
        )

        self.assertEqual(employee.tenenet_number, 123)
        self.assertEqual(employee.title_academic, "Mgr.")
        self.assertEqual(employee.first_name, "Test")
        self.assertEqual(employee.last_name, "Zamestnanec")
        self.assertEqual(employee.name, "Mgr. Test Zamestnanec")
        self.assertEqual(employee.legal_name, "Test Zamestnanec")
        self.assertEqual(employee.tenenet_list_first_name, "Test")
        self.assertEqual(employee.tenenet_list_last_name, "Zamestnanec")
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
        self.assertEqual(employee.tenenet_list_first_name, "Novy")
        self.assertEqual(employee.tenenet_list_last_name, "Zamestnanec")

        second_employee = self.env["hr.employee"].create({
            "name": "Druhy Zamestnanec",
            "position": "Sociálny pracovník",
        })
        self.assertEqual(second_employee.position_catalog_id, employee.position_catalog_id)

    def test_hr_employee_list_name_parts(self):
        structured_employee = self.env["hr.employee"].create({
            "name": "Adam Martin Zamestnanec",
            "first_name": "Adam Martin",
            "last_name": "Zamestnanec",
        })
        structured_employee_with_split_surname = self.env["hr.employee"].create({
            "name": "Jana Budinská Veličová",
            "first_name": "Jana",
            "last_name": "Budinská Veličová",
        })
        combined_employee = self.env["hr.employee"].create({
            "name": "Adam Martin Zamestnanec",
        })
        single_name_employee = self.env["hr.employee"].create({
            "name": "Administrator",
        })

        self.assertEqual(structured_employee.tenenet_list_first_name, "Adam Martin")
        self.assertEqual(structured_employee.tenenet_list_last_name, "Zamestnanec")
        self.assertEqual(structured_employee_with_split_surname.tenenet_list_first_name, "Jana Budinská")
        self.assertEqual(structured_employee_with_split_surname.tenenet_list_last_name, "Veličová")
        self.assertEqual(combined_employee.tenenet_list_first_name, "Adam Martin")
        self.assertEqual(combined_employee.tenenet_list_last_name, "Zamestnanec")
        self.assertEqual(single_name_employee.tenenet_list_first_name, "Administrator")
        self.assertFalse(single_name_employee.tenenet_list_last_name)

    def test_hr_employee_tenenet_page_is_renamed_to_mzdy(self):
        view = self.env.ref("tenenet_projects.view_hr_employee_form_tenenet")

        self.assertIn('string="MZDY"', view.arch_db)
        self.assertNotIn('page string="TENENET"', view.arch_db)

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
            }
        )
        project = self.env["tenenet.project"].create(
            {
                "name": "Linked Project",
                "program_ids": [(4, program.id)],
                "reporting_program_id": program.id,
                "donor_id": donor.id,
            }
        )

        project.write({
            "program_ids": [(3, program.id)],
            "reporting_program_id": False,
        })
        program.unlink()

        self.assertFalse(project.exists().program_ids)
