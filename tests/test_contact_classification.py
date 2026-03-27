from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetContactClassification(TransactionCase):
    def test_client_partner_flags_drive_contact_actions(self):
        client = self.env["res.partner"].create({
            "name": "Klient",
            "is_tenenet_client": True,
        })
        partner = self.env["res.partner"].create({
            "name": "Partner",
            "is_tenenet_partner": True,
        })
        both = self.env["res.partner"].create({
            "name": "Klient Partner",
            "is_tenenet_client": True,
            "is_tenenet_partner": True,
        })
        neutral = self.env["res.partner"].create({"name": "Neutral"})

        client_domain = eval(self.env.ref("tenenet_projects.action_tenenet_clients").domain)
        partner_domain = eval(self.env.ref("tenenet_projects.action_tenenet_partners").domain)

        client_records = self.env["res.partner"].search(client_domain)
        partner_records = self.env["res.partner"].search(partner_domain)

        self.assertIn(client, client_records)
        self.assertNotIn(client, partner_records)
        self.assertIn(partner, partner_records)
        self.assertNotIn(partner, client_records)
        self.assertIn(both, client_records)
        self.assertIn(both, partner_records)
        self.assertNotIn(neutral, client_records)
        self.assertNotIn(neutral, partner_records)

    def test_employee_contact_flag_is_computed_from_work_contact(self):
        partner = self.env["res.partner"].create({"name": "Employee Contact"})
        self.env["hr.employee"].create({
            "name": "Employee Contact",
            "work_contact_id": partner.id,
        })

        partner.invalidate_recordset()
        self.assertTrue(partner.is_tenenet_employee_contact)
        self.assertIn("Zamestnanec", partner.tenenet_contact_role_summary)
