from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetEmployeeService(TransactionCase):
    def setUp(self):
        super().setUp()
        self.base_user_group = self.env.ref("base.group_user")
        self.hr_user_group = self.env.ref("hr.group_hr_user")
        self.hr_manager_group = self.env.ref("hr.group_hr_manager")

        self.regular_user = self._create_user("regular.user", [self.base_user_group.id])
        self.grand_manager_user = self._create_user("grand.manager", [self.hr_user_group.id])
        self.manager_user = self._create_user("manager.user", [self.hr_user_group.id])
        self.employee_user = self._create_user("employee.user", [self.hr_user_group.id])
        self.outsider_user = self._create_user("outsider.user", [self.hr_user_group.id])
        self.hr_manager_user = self._create_user("hr.manager.user", [self.hr_manager_group.id])

        self.grand_manager = self.env["hr.employee"].create({
            "name": "Grand Manager",
            "user_id": self.grand_manager_user.id,
        })
        self.manager = self.env["hr.employee"].create({
            "name": "Direct Manager",
            "user_id": self.manager_user.id,
            "parent_id": self.grand_manager.id,
        })
        self.employee = self.env["hr.employee"].create({
            "name": "Target Employee",
            "user_id": self.employee_user.id,
            "parent_id": self.manager.id,
        })
        self.outsider = self.env["hr.employee"].create({
            "name": "Outsider Employee",
            "user_id": self.outsider_user.id,
        })
        self.regular_employee = self.env["hr.employee"].create({
            "name": "Regular Employee",
            "user_id": self.regular_user.id,
        })
        self.service_model = self.env["tenenet.employee.service"]

    def _create_user(self, login, group_ids):
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": login,
            "login": login,
            "email": f"{login}@example.com",
            "group_ids": [(6, 0, group_ids)],
        })

    def test_employee_collects_all_manager_users_for_services(self):
        manager_users = self.employee.service_manager_user_ids

        self.assertIn(self.manager_user, manager_users)
        self.assertIn(self.grand_manager_user, manager_users)
        self.assertNotIn(self.employee_user, manager_users)
        self.assertNotIn(self.outsider_user, manager_users)

    def test_higher_up_can_manage_employee_services(self):
        service = self.service_model.with_user(self.manager_user).create({
            "employee_id": self.employee.id,
            "name": "Krizova intervencia",
        })

        self.assertEqual(service.employee_id, self.employee)
        self.assertEqual(service.name, "Krizova intervencia")
        self.assertEqual(service.service_catalog_id.name, "Krizova intervencia")

        service.with_user(self.grand_manager_user).write({"name": "Supervizia"})
        self.assertEqual(service.name, "Supervizia")
        self.assertEqual(service.service_catalog_id.name, "Supervizia")

    def test_service_catalog_remembers_services_for_reuse(self):
        first_service = self.service_model.with_user(self.manager_user).create({
            "employee_id": self.employee.id,
            "name": "Dlhové poradenstvo",
        })
        second_service = self.service_model.with_user(self.manager_user).create({
            "employee_id": self.employee.id,
            "service_catalog_id": first_service.service_catalog_id.id,
        })

        self.assertEqual(first_service.service_catalog_id, second_service.service_catalog_id)
        self.assertEqual(second_service.name, "Dlhové poradenstvo")

    def test_employee_and_unrelated_hr_user_cannot_manage_services(self):
        service = self.service_model.create({
            "employee_id": self.employee.id,
            "name": "Socialne poradenstvo",
        })

        self.assertEqual(service.with_user(self.employee_user).name, "Socialne poradenstvo")
        self.assertEqual(service.with_user(self.outsider_user).name, "Socialne poradenstvo")

        with self.assertRaises(AccessError):
            self.service_model.with_user(self.employee_user).create({
                "employee_id": self.employee.id,
                "name": "Case management",
            })

        with self.assertRaises(AccessError):
            self.service_model.with_user(self.outsider_user).create({
                "employee_id": self.employee.id,
                "name": "Dlhové poradenstvo",
            })

        with self.assertRaises(AccessError):
            service.with_user(self.employee_user).write({"name": "Zmena"})

        with self.assertRaises(AccessError):
            service.with_user(self.outsider_user).unlink()

    def test_regular_employee_can_read_services_in_public_profile(self):
        service = self.service_model.create({
            "employee_id": self.employee.id,
            "name": "Socialne poradenstvo",
        })

        public_employee = self.env["hr.employee.public"].with_user(self.regular_user).browse(self.employee.id)

        self.assertEqual(service.with_user(self.regular_user).name, "Socialne poradenstvo")
        self.assertEqual(public_employee.service_ids.mapped("name"), ["Socialne poradenstvo"])

        with self.assertRaises(AccessError):
            self.service_model.with_user(self.regular_user).create({
                "employee_id": self.employee.id,
                "name": "Neopravnena zmena",
            })

    def test_service_requires_at_least_one_delivery_mode(self):
        with self.assertRaises(ValidationError):
            self.service_model.create({
                "employee_id": self.employee.id,
                "name": "Krízová intervencia",
                "delivery_online": False,
                "delivery_in_person": False,
            })

        service = self.service_model.create({
            "employee_id": self.employee.id,
            "name": "Krízová intervencia",
            "delivery_online": True,
            "delivery_in_person": False,
        })

        self.assertTrue(service.delivery_online)
        self.assertFalse(service.delivery_in_person)

    def test_hr_manager_has_full_access(self):
        service = self.service_model.with_user(self.hr_manager_user).create({
            "employee_id": self.employee.id,
            "name": "Terénna práca",
        })

        self.assertTrue(service.exists())
        service.with_user(self.hr_manager_user).unlink()
        self.assertFalse(service.exists())
