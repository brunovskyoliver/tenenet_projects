from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetProjectSites(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({
            "name": "Zodpovedná osoba",
            "work_ratio": 100.0,
        })
        self.employee2 = self.env["hr.employee"].create({
            "name": "Druhá osoba",
            "work_ratio": 100.0,
        })
        self.landlord = self.env["res.partner"].create({"name": "Prenajímateľ"})
        self.project = self.env["tenenet.project"].create({"name": "Projekt Prevádzky"})
        self.project2 = self.env["tenenet.project"].create({"name": "Projekt Terén"})
        self.assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.project.id,
            "allocation_ratio": 100.0,
            "wage_hm": 10.0,
        })
        self.company = self.env.company
        base_user_group = self.env.ref("base.group_user")
        tenenet_user_group = self.env.ref("tenenet_projects.group_tenenet_user")
        tenenet_manager_group = self.env.ref("tenenet_projects.group_tenenet_manager")
        self.user_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Použ. Prevádzky",
                "login": "site_user",
                "email": "site_user@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([base_user_group.id, tenenet_user_group.id])],
            }
        )
        self.manager_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Manažér Prevádzky",
                "login": "site_manager",
                "email": "site_manager@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([base_user_group.id, tenenet_manager_group.id])],
            }
        )

    def _site_vals(self, **overrides):
        vals = {
            "name": "Bratislava",
            "site_type": "prevadzka",
            "responsible_employee_id": self.employee.id,
            "email": "prevadzka@test.sk",
            "phone": "+421900000000",
            "street": "Ulica 1",
            "street2": "2. poschodie",
            "zip": "81101",
            "city": "Bratislava",
            "landlord_partner_id": self.landlord.id,
        }
        vals.update(overrides)
        return vals

    def test_site_creation_with_structured_fields(self):
        prevadzka = self.env["tenenet.project.site"].create(self._site_vals())
        centrum = self.env["tenenet.project.site"].create(
            self._site_vals(name="Centrum", site_type="centrum")
        )
        teren = self.env["tenenet.project.site"].create(
            self._site_vals(name="Terén", site_type="teren", city="Košice")
        )

        self.assertEqual(prevadzka.responsible_employee_id, self.employee)
        self.assertEqual(prevadzka.landlord_partner_id, self.landlord)
        self.assertEqual(prevadzka.city, "Bratislava")
        self.assertEqual(centrum.site_type, "centrum")
        self.assertEqual(teren.site_type, "teren")

    def test_project_can_link_mixed_site_types(self):
        prevadzka = self.env["tenenet.project.site"].create(self._site_vals())
        centrum = self.env["tenenet.project.site"].create(
            self._site_vals(name="Centrum", site_type="centrum")
        )
        teren = self.env["tenenet.project.site"].create(
            self._site_vals(name="Terén", site_type="teren")
        )

        self.project.write({
            "site_ids": [
                Command.link(prevadzka.id),
                Command.link(centrum.id),
                Command.link(teren.id),
            ]
        })

        self.assertEqual(set(self.project.site_ids.ids), {prevadzka.id, centrum.id, teren.id})
        self.assertIn(self.project, prevadzka.project_ids)
        self.assertIn(self.project, centrum.project_ids)
        self.assertIn(self.project, teren.project_ids)

    def test_site_wizard_filters_type_and_excludes_linked_records(self):
        linked_prevadzka = self.env["tenenet.project.site"].create(self._site_vals(name="Linked"))
        available_prevadzka = self.env["tenenet.project.site"].create(self._site_vals(name="Available"))
        centrum = self.env["tenenet.project.site"].create(
            self._site_vals(name="Centrum", site_type="centrum")
        )
        self.project.write({"site_ids": [Command.link(linked_prevadzka.id)]})

        wizard = self.env["tenenet.project.site.wizard"].with_context(
            default_project_id=self.project.id
        ).create({"project_id": self.project.id, "site_type": "prevadzka"})
        wizard._compute_available_site_ids()

        self.assertIn(available_prevadzka, wizard.available_site_ids)
        self.assertNotIn(linked_prevadzka, wizard.available_site_ids)
        self.assertNotIn(centrum, wizard.available_site_ids)

        wizard.write({"site_ids": [Command.set([available_prevadzka.id])]})
        wizard.action_confirm()

        self.assertIn(available_prevadzka, self.project.site_ids)

    def test_assignment_accepts_multiple_project_sites(self):
        prevadzka = self.env["tenenet.project.site"].create(self._site_vals())
        teren = self.env["tenenet.project.site"].create(
            self._site_vals(name="Terén", site_type="teren")
        )
        self.project.write({"site_ids": [Command.link(prevadzka.id), Command.link(teren.id)]})

        self.assignment.write({"site_ids": [Command.set([prevadzka.id, teren.id])]})

        self.assertEqual(set(self.assignment.site_ids.ids), {prevadzka.id, teren.id})

    def test_assignment_rejects_site_outside_project(self):
        external_site = self.env["tenenet.project.site"].create(
            self._site_vals(name="Externá", responsible_employee_id=self.employee2.id)
        )
        self.project2.write({"site_ids": [Command.link(external_site.id)]})

        with self.assertRaises(ValidationError):
            self.assignment.write({"site_ids": [Command.set([external_site.id])]})

    def test_unlinking_site_from_project_cleans_assignment_links(self):
        prevadzka = self.env["tenenet.project.site"].create(self._site_vals())
        self.project.write({"site_ids": [Command.link(prevadzka.id)]})
        self.assignment.write({"site_ids": [Command.set([prevadzka.id])]})

        self.project.write({"site_ids": [Command.unlink(prevadzka.id)]})

        self.assertFalse(self.assignment.site_ids)
        self.assertNotIn(prevadzka, self.project.site_ids)

    def test_site_acl_user_read_only_manager_full(self):
        site_model_user = self.env["tenenet.project.site"].with_user(self.user_user)
        site_model_manager = self.env["tenenet.project.site"].with_user(self.manager_user)

        site = site_model_manager.create(self._site_vals())
        self.assertTrue(site.exists())

        with self.assertRaises(AccessError):
            site_model_user.create(self._site_vals(name="User blocked"))

        self.assertEqual(site_model_user.search_count([("id", "=", site.id)]), 1)
