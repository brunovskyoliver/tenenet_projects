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
        key = self.env["tenenet.employee.site.key"].create({
            "employee_id": self.employee.id,
            "site_id": self.site_prevadzka.id,
            "note": "Hlavný zväzok",
        })

        self.assertEqual(key.site_id, self.site_prevadzka)
        self.assertIn(key, self.employee.site_key_ids)
        self.assertIn(key, self.site_prevadzka.site_key_ids)

    def test_site_key_created_from_site_side_visible_on_employee(self):
        key = self.env["tenenet.employee.site.key"].create({
            "employee_id": self.employee.id,
            "site_id": self.site_centrum.id,
            "note": "Bočný vstup",
        })

        self.assertIn(key, self.site_centrum.site_key_ids)
        self.assertIn(key, self.employee.site_key_ids)

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
