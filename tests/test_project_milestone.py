from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProjectMilestone(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.base_user_group = self.env.ref("base.group_user")
        self.tenenet_user_group = self.env.ref("tenenet_projects.group_tenenet_user")
        self.tenenet_manager_group = self.env.ref("tenenet_projects.group_tenenet_manager")

        self.garant_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Garant Míľnik",
            "login": "milestone_garant",
            "email": "milestone_garant@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.base_user_group.id, self.tenenet_user_group.id])],
        })
        self.pm_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "PM Míľnik",
            "login": "milestone_pm",
            "email": "milestone_pm@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.base_user_group.id, self.tenenet_user_group.id])],
        })
        self.normal_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Používateľ Míľnik",
            "login": "milestone_user",
            "email": "milestone_user@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.base_user_group.id, self.tenenet_user_group.id])],
        })
        self.manager_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Manažér Míľnik",
            "login": "milestone_manager",
            "email": "milestone_manager@example.com",
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
            "group_ids": [Command.set([self.base_user_group.id, self.tenenet_manager_group.id])],
        })

        self.garant_employee = self.env["hr.employee"].create({
            "name": "Garant projektu",
            "user_id": self.garant_user.id,
        })
        self.pm_employee = self.env["hr.employee"].create({
            "name": "Projektový manažér",
            "user_id": self.pm_user.id,
        })
        self.project = self.env["tenenet.project"].create({
            "name": "Projekt s míľnikmi",
            "odborny_garant_id": self.garant_employee.id,
            "project_manager_id": self.pm_employee.id,
            "date_start": "2026-01-01",
            "date_end": "2026-12-31",
        })

    def _milestone_vals(self, **overrides):
        vals = {
            "project_id": self.project.id,
            "name": "Podpis zmluvy",
            "date": "2026-02-15",
            "note": "Termín podpisu zmluvy",
        }
        vals.update(overrides)
        return vals

    def test_garant_can_create_milestone(self):
        milestone = self.env["tenenet.project.milestone"].with_user(self.garant_user).create(
            self._milestone_vals()
        )
        self.assertEqual(milestone.project_id, self.project)

    def test_manager_can_create_milestone(self):
        milestone = self.env["tenenet.project.milestone"].with_user(self.manager_user).create(
            self._milestone_vals(name="Manažérsky míľnik")
        )
        self.assertEqual(milestone.name, "Manažérsky míľnik")

    def test_pm_cannot_create_milestone(self):
        with self.assertRaises(AccessError):
            self.env["tenenet.project.milestone"].with_user(self.pm_user).create(
                self._milestone_vals()
            )

    def test_regular_user_cannot_create_milestone(self):
        with self.assertRaises(AccessError):
            self.env["tenenet.project.milestone"].with_user(self.normal_user).create(
                self._milestone_vals()
            )

    def test_wizard_creates_milestone_for_garant(self):
        wizard = self.env["tenenet.project.milestone.wizard"].with_user(self.garant_user).create({
            "project_id": self.project.id,
            "name": "Odovzdanie výstupu",
            "date": "2026-09-01",
            "note": "Dôležitý termín",
        })
        wizard.action_confirm()
        milestone = self.project.milestone_ids.filtered(lambda item: item.name == "Odovzdanie výstupu")
        self.assertTrue(milestone)

    def test_pm_cannot_update_existing_milestone(self):
        milestone = self.env["tenenet.project.milestone"].with_user(self.manager_user).create(
            self._milestone_vals()
        )
        with self.assertRaises(AccessError):
            milestone.with_user(self.pm_user).write({"name": "Neoprávnená zmena"})
