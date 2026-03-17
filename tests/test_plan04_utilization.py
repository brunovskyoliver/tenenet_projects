from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan04Utilization(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({"name": "Zamestnanec Vyťaženosť"})
        self.manager = self.env["hr.employee"].create({"name": "Manažér Vyťaženosť"})
        self.company = self.env.company
        base_user_group = self.env.ref("base.group_user")
        tenenet_user_group = self.env.ref("tenenet_projects.group_tenenet_user")
        tenenet_manager_group = self.env.ref("tenenet_projects.group_tenenet_manager")

        self.user_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Používateľ Vyťaženosť",
                "login": "utilization_user",
                "email": "utilization_user@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([base_user_group.id, tenenet_user_group.id])],
            }
        )
        self.manager_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Manažér Vyťaženosť",
                "login": "utilization_manager",
                "email": "utilization_manager@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([base_user_group.id, tenenet_manager_group.id])],
            }
        )

    def _utilization_vals(self, **overrides):
        vals = {
            "employee_id": self.employee.id,
            "period": "2026-02-01",
            "manager_id": self.manager.id,
            "work_ratio": 100.0,
            "capacity_hours": 100.0,
            "hours_pp": 30.0,
            "hours_np": 20.0,
            "hours_travel": 10.0,
            "hours_training": 5.0,
            "hours_ambulance": 3.0,
            "hours_international": 2.0,
            "hours_vacation": 10.0,
            "hours_doctor": 5.0,
            "hours_sick": 8.0,
            "hours_ballast": 2.0,
        }
        vals.update(overrides)
        return vals

    def test_utilization_computed_fields(self):
        utilization = self.env["tenenet.utilization"].create(self._utilization_vals())

        self.assertEqual(utilization.hours_project_total, 70.0)
        self.assertEqual(utilization.hours_non_project_total, 25.0)
        self.assertAlmostEqual(utilization.utilization_rate, 0.7, places=4)
        self.assertEqual(utilization.utilization_status, "warning")
        self.assertAlmostEqual(utilization.non_project_rate, 0.25, places=4)
        self.assertEqual(utilization.non_project_status, "ok")
        self.assertEqual(utilization.hours_diff, -5.0)
        self.assertEqual(utilization.manager_id, self.manager)
        self.assertEqual(utilization.manager_name, "Manažér Vyťaženosť")

    def test_utilization_threshold_boundaries(self):
        utilization = self.env["tenenet.utilization"].create(
            self._utilization_vals(
                period="2026-03-01",
                hours_pp=50.0,
                hours_np=20.0,
                hours_travel=5.0,
                hours_training=5.0,
                hours_ambulance=0.0,
                hours_international=0.0,
                hours_vacation=10.0,
                hours_doctor=10.0,
                hours_sick=5.0,
                hours_ballast=0.0,
            )
        )

        self.assertAlmostEqual(utilization.utilization_rate, 0.8, places=4)
        self.assertEqual(utilization.utilization_status, "ok")
        self.assertAlmostEqual(utilization.non_project_rate, 0.25, places=4)
        self.assertEqual(utilization.non_project_status, "ok")

    def test_non_project_status_warning_above_threshold(self):
        utilization = self.env["tenenet.utilization"].create(
            self._utilization_vals(
                period="2026-07-01",
                hours_vacation=10.0,
                hours_doctor=10.0,
                hours_sick=5.0,
                hours_ballast=1.0,
            )
        )

        self.assertEqual(utilization.hours_non_project_total, 26.0)
        self.assertAlmostEqual(utilization.non_project_rate, 0.26, places=4)
        self.assertEqual(utilization.non_project_status, "warning")

    def test_utilization_division_by_zero(self):
        utilization = self.env["tenenet.utilization"].create(
            self._utilization_vals(
                period="2026-04-01",
                capacity_hours=0.0,
                hours_pp=10.0,
                hours_np=0.0,
                hours_travel=0.0,
                hours_training=0.0,
                hours_ambulance=0.0,
                hours_international=0.0,
                hours_vacation=5.0,
                hours_doctor=0.0,
                hours_sick=0.0,
                hours_ballast=0.0,
            )
        )

        self.assertAlmostEqual(utilization.utilization_rate, 0.0, places=4)
        self.assertAlmostEqual(utilization.non_project_rate, 0.0, places=4)
        self.assertEqual(utilization.utilization_status, "warning")
        self.assertEqual(utilization.non_project_status, "ok")
        self.assertEqual(utilization.hours_diff, 15.0)

    def test_utilization_unique_constraint(self):
        self.env["tenenet.utilization"].create(self._utilization_vals(period="2026-05-01"))

        with self.cr.savepoint():
            with self.assertRaises(IntegrityError):
                self.env["tenenet.utilization"].create(self._utilization_vals(period="2026-05-01"))

    def test_utilization_acl_user_read_only_manager_full(self):
        with self.assertRaises(AccessError):
            self.env["tenenet.utilization"].with_user(self.user_user).create(
                self._utilization_vals(period="2026-06-01")
            )

        utilization = self.env["tenenet.utilization"].with_user(self.manager_user).create(
            self._utilization_vals(period="2026-06-01")
        )

        self.assertTrue(utilization.exists())
