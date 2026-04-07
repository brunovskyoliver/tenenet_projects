from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetProjectContacts(TransactionCase):
    def setUp(self):
        super().setUp()
        self.project = self.env["tenenet.project"].create({"name": "Projekt Kontakty"})
        self.project2 = self.env["tenenet.project"].create({"name": "Projekt Kontakty 2"})
        self.company = self.env.company
        base_user_group = self.env.ref("base.group_user")
        tenenet_user_group = self.env.ref("tenenet_projects.group_tenenet_user")
        tenenet_manager_group = self.env.ref("tenenet_projects.group_tenenet_manager")
        self.user_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Použ. Kontakty",
                "login": "contact_user",
                "email": "contact_user@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([base_user_group.id, tenenet_user_group.id])],
            }
        )
        self.manager_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Manažér Kontakty",
                "login": "contact_manager",
                "email": "contact_manager@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([base_user_group.id, tenenet_manager_group.id])],
            }
        )

    def _contact_vals(self, **overrides):
        vals = {
            "name": "Hlavný kontakt",
            "email": "kontakt@test.sk",
            "phone": "0900123456",
            "note": "Preferovaný kontakt",
            "website": "https://www.tenenet.sk",
        }
        vals.update(overrides)
        return vals

    def test_contact_creation_with_structured_fields(self):
        contact = self.env["tenenet.project.contact"].create(self._contact_vals())

        self.assertEqual(contact.name, "Hlavný kontakt")
        self.assertEqual(contact.email, "kontakt@test.sk")
        self.assertEqual(contact.phone, "+421 900 123 456")
        self.assertEqual(contact.note, "Preferovaný kontakt")
        self.assertEqual(contact.website, "https://www.tenenet.sk")

    def test_contact_creation_with_name_only(self):
        contact = self.env["tenenet.project.contact"].create({"name": "Iba meno"})

        self.assertEqual(contact.name, "Iba meno")
        self.assertFalse(contact.email)
        self.assertFalse(contact.phone)
        self.assertFalse(contact.note)
        self.assertFalse(contact.website)

    def test_contact_rejects_invalid_email(self):
        with self.assertRaises(ValidationError):
            self.env["tenenet.project.contact"].create(self._contact_vals(email="zly-email"))

    def test_contact_rejects_invalid_phone(self):
        with self.assertRaises(ValidationError):
            self.env["tenenet.project.contact"].create(self._contact_vals(phone="12345"))

    def test_project_can_reuse_contact_on_multiple_projects(self):
        contact = self.env["tenenet.project.contact"].create(self._contact_vals())

        self.project.write({"contact_ids": [Command.link(contact.id)]})
        self.project2.write({"contact_ids": [Command.link(contact.id)]})

        self.assertIn(contact, self.project.contact_ids)
        self.assertIn(contact, self.project2.contact_ids)
        self.assertEqual(set(contact.project_ids.ids), {self.project.id, self.project2.id})

    def test_contact_wizard_excludes_already_linked_records(self):
        linked_contact = self.env["tenenet.project.contact"].create(self._contact_vals(name="Linked"))
        available_contact = self.env["tenenet.project.contact"].create(self._contact_vals(name="Available"))
        self.project.write({"contact_ids": [Command.link(linked_contact.id)]})

        wizard = self.env["tenenet.project.contact.wizard"].with_context(
            default_project_id=self.project.id
        ).create({"project_id": self.project.id})
        wizard._compute_available_contact_ids()

        self.assertIn(available_contact, wizard.available_contact_ids)
        self.assertNotIn(linked_contact, wizard.available_contact_ids)

        wizard.write({"contact_ids": [Command.set([available_contact.id])]})
        wizard.action_confirm()

        self.assertIn(available_contact, self.project.contact_ids)

    def test_unlink_contact_from_one_project_keeps_shared_record(self):
        contact = self.env["tenenet.project.contact"].create(self._contact_vals())
        self.project.write({"contact_ids": [Command.link(contact.id)]})
        self.project2.write({"contact_ids": [Command.link(contact.id)]})

        self.project.write({"contact_ids": [Command.unlink(contact.id)]})

        self.assertNotIn(contact, self.project.contact_ids)
        self.assertIn(contact, self.project2.contact_ids)
        self.assertTrue(contact.exists())

    def test_contact_acl_user_read_only_manager_full(self):
        contact_model_user = self.env["tenenet.project.contact"].with_user(self.user_user)
        contact_model_manager = self.env["tenenet.project.contact"].with_user(self.manager_user)

        contact = contact_model_manager.create(self._contact_vals())
        self.assertTrue(contact.exists())

        with self.assertRaises(AccessError):
            contact_model_user.create(self._contact_vals(name="User blocked"))

        self.assertEqual(contact_model_user.search_count([("id", "=", contact.id)]), 1)
