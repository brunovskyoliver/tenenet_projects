from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetEmployeeAssets(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({
            "name": "Majetkový Zamestnanec",
            "work_ratio": 100.0,
        })
        self.employee2 = self.env["hr.employee"].create({
            "name": "Druhý Zamestnanec",
            "work_ratio": 100.0,
        })
        self.asset_type_laptop = self.env["tenenet.employee.asset.type"].create({
            "name": "Laptop",
        })
        self.asset_type_phone = self.env["tenenet.employee.asset.type"].create({
            "name": "Mobil",
        })
        self.site_prevadzka = self.env["tenenet.project.site"].create({
            "name": "Prevádzka Test",
            "site_type": "prevadzka",
        })
        self.site_centrum = self.env["tenenet.project.site"].create({
            "name": "Centrum Test",
            "site_type": "centrum",
        })
        self.site_teren = self.env["tenenet.project.site"].create({
            "name": "Terén Test",
            "site_type": "teren",
        })
        self.company = self.env.company
        self.base_user_group = self.env.ref("base.group_user")
        self.tenenet_user_group = self.env.ref("tenenet_projects.group_tenenet_user")
        self.tenenet_manager_group = self.env.ref("tenenet_projects.group_tenenet_manager")
        self.user_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Použ. Majetok",
                "login": "asset_user",
                "email": "asset_user@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([self.base_user_group.id, self.tenenet_user_group.id])],
            }
        )
        self.manager_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Manažér Majetok",
                "login": "asset_manager",
                "email": "asset_manager@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([self.base_user_group.id, self.tenenet_manager_group.id])],
            }
        )

    def test_employee_asset_creation(self):
        asset = self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_laptop.id,
            "cost": 1200.0,
            "note": "Inventár 123",
        })

        self.assertEqual(asset.employee_id, self.employee)
        self.assertEqual(asset.asset_type_id, self.asset_type_laptop)
        self.assertEqual(asset.name, "Laptop")
        self.assertEqual(asset.cost, 1200.0)
        self.assertEqual(asset.note, "Inventár 123")

    def test_employee_asset_total_value_uses_active_assets(self):
        self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_laptop.id,
            "cost": 1200.0,
        })
        self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_phone.id,
            "cost": 300.0,
        })
        self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_phone.id,
            "cost": 50.0,
            "active": False,
        })

        self.assertEqual(self.employee.asset_total_value, 1500.0)

    def test_site_key_created_from_employee_side_visible_on_site(self):
        self.employee.work_phone = "+421 900 111 222"
        key = self.env["tenenet.employee.site.key"].create({
            "employee_id": self.employee.id,
            "site_id": self.site_prevadzka.id,
        })

        self.assertEqual(key.site_id, self.site_prevadzka)
        self.assertIn(key, self.employee.site_key_ids)
        self.assertIn(key, self.site_prevadzka.site_key_ids)
        self.assertEqual(key.work_phone, "+421 900 111 222")

    def test_site_key_created_from_site_side_visible_on_employee(self):
        key = self.env["tenenet.employee.site.key"].create({
            "employee_id": self.employee.id,
            "site_id": self.site_centrum.id,
        })

        self.assertIn(key, self.site_centrum.site_key_ids)
        self.assertIn(key, self.employee.site_key_ids)

    def test_employee_supports_work_and_private_phone(self):
        self.employee.write({
            "work_phone": "+421 900 123 456",
            "private_phone": "+421 901 654 321",
        })

        self.assertEqual(self.employee.work_phone, "+421 900 123 456")
        self.assertEqual(self.employee.private_phone, "+421 901 654 321")

    def test_employee_form_does_not_duplicate_language_skill_editor_on_tenenet_tab(self):
        arch = self.env["hr.employee"].get_view(
            view_id=self.env.ref("tenenet_projects.view_hr_employee_form_tenenet").id,
            view_type="form",
        )["arch"]
        root = etree.fromstring(arch.encode())

        language_fields = root.xpath(
            "//page[@string='TENENET']//field[@name='current_employee_skill_ids']"
        )
        self.assertFalse(
            language_fields,
            "Expected language skills to stay only in the standard Zivotopis section.",
        )

    def test_employee_form_contains_work_and_private_phone_in_personal_tab(self):
        arch = self.env["hr.employee"].get_view(
            view_id=self.env.ref("tenenet_projects.view_hr_employee_form_tenenet").id,
            view_type="form",
        )["arch"]
        root = etree.fromstring(arch.encode())

        personal_work_phone = root.xpath(
            "//page[@name='personal_information']//field[@name='work_phone']"
        )
        personal_private_phone = root.xpath(
            "//page[@name='personal_information']//field[@name='private_phone']"
        )

        self.assertTrue(personal_work_phone, "Expected work phone on the Personal tab.")
        self.assertTrue(personal_private_phone, "Expected private phone on the Personal tab.")
        self.assertIn(
            "parent_id.user_id != uid",
            personal_private_phone[0].get("invisible", ""),
        )

    def test_site_key_rejects_teren(self):
        with self.assertRaises(ValidationError):
            self.env["tenenet.employee.site.key"].create({
                "employee_id": self.employee.id,
                "site_id": self.site_teren.id,
            })

    def test_site_key_unique_per_employee_and_site(self):
        self.env["tenenet.employee.site.key"].create({
            "employee_id": self.employee.id,
            "site_id": self.site_prevadzka.id,
        })

        with self.assertRaises(Exception):
            self.env["tenenet.employee.site.key"].create({
                "employee_id": self.employee.id,
                "site_id": self.site_prevadzka.id,
            })

    def test_asset_acl_user_read_only_manager_full(self):
        asset_model_user = self.env["tenenet.employee.asset"].with_user(self.user_user)
        asset_model_manager = self.env["tenenet.employee.asset"].with_user(self.manager_user)

        asset = asset_model_manager.create({
            "employee_id": self.employee.id,
            "asset_type_id": self.asset_type_laptop.id,
        })
        self.assertTrue(asset.exists())
        self.assertEqual(asset_model_user.search_count([("id", "=", asset.id)]), 1)

        with self.assertRaises(AccessError):
            asset_model_user.create({
                "employee_id": self.employee.id,
                "asset_type_id": self.asset_type_phone.id,
            })

    def test_site_key_acl_user_read_only_manager_full(self):
        key_model_user = self.env["tenenet.employee.site.key"].with_user(self.user_user)
        key_model_manager = self.env["tenenet.employee.site.key"].with_user(self.manager_user)

        key = key_model_manager.create({
            "employee_id": self.employee.id,
            "site_id": self.site_prevadzka.id,
        })
        self.assertTrue(key.exists())
        self.assertEqual(key_model_user.search_count([("id", "=", key.id)]), 1)

        with self.assertRaises(AccessError):
            key_model_user.create({
                "employee_id": self.employee2.id,
                "site_id": self.site_centrum.id,
            })

    def test_employee_form_site_key_subview_does_not_request_note(self):
        arch = self.env["hr.employee"].get_view(
            view_id=self.env.ref("tenenet_projects.view_hr_employee_form_tenenet").id,
            view_type="form",
        )["arch"]
        self._assert_site_key_subview_has_no_note(arch)

    def test_project_site_form_site_key_subview_does_not_request_note(self):
        arch = self.env["tenenet.project.site"].get_view(
            view_id=self.env.ref("tenenet_projects.view_tenenet_project_site_form").id,
            view_type="form",
        )["arch"]
        self._assert_site_key_subview_has_no_note(arch)

    def _assert_site_key_subview_has_no_note(self, arch):
        root = etree.fromstring(arch.encode())
        site_key_fields = root.xpath("//field[@name='site_key_ids']")
        self.assertTrue(site_key_fields, "Expected a site_key_ids subview in the form architecture.")
        self.assertFalse(
            root.xpath("//field[@name='site_key_ids']//field[@name='note']"),
            "site_key_ids subview should not request note on tenenet.employee.site.key.",
        )
