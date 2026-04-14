from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetEmployeeProfileRework(TransactionCase):
    def setUp(self):
        super().setUp()
        self.base_user_group = self.env.ref("base.group_user")
        self.hr_manager_group = self.env.ref("hr.group_hr_manager")

        self.manager_user = self._create_user("profile.manager", [self.base_user_group.id])
        self.employee_user = self._create_user("profile.employee", [self.base_user_group.id])
        self.outsider_user = self._create_user("profile.outsider", [self.base_user_group.id])
        self.hr_manager_user = self._create_user("profile.hr.manager", [self.hr_manager_group.id])

        self.manager = self.env["hr.employee"].create({
            "name": "Mgr. Manažér",
            "user_id": self.manager_user.id,
        })
        self.employee = self.env["hr.employee"].create({
            "name": "Adam Profil",
            "user_id": self.employee_user.id,
            "parent_id": self.manager.id,
            "experience_years_total": 5.0,
        })
        self.outsider = self.env["hr.employee"].create({
            "name": "Eva Outsider",
            "user_id": self.outsider_user.id,
        })

        self.site_main = self.env["tenenet.project.site"].create({
            "name": "Bratislava centrum",
            "site_type": "centrum",
        })
        self.site_secondary = self.env["tenenet.project.site"].create({
            "name": "Trnava prevádzka",
            "site_type": "prevadzka",
        })
        self.site_terrain = self.env["tenenet.project.site"].create({
            "name": "Bratislavský samosprávny kraj",
            "site_type": "teren",
            "kraj": "Bratislavský samosprávny kraj",
        })

        self.job_primary = self.env["hr.job"].create({"name": "Psychológ"})
        self.job_secondary = self.env["hr.job"].create({"name": "Koordinátor"})
        self.employee.write({
            "job_id": self.job_primary.id,
            "additional_job_ids": [Command.set(self.job_secondary.ids)],
            "main_site_id": self.site_main.id,
            "secondary_site_ids": [Command.set(self.site_secondary.ids)],
        })

    def _create_user(self, login, group_ids):
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": login,
            "login": login,
            "email": f"{login}@example.com",
            "company_id": self.env.company.id,
            "company_ids": [Command.set([self.env.company.id])],
            "group_ids": [Command.set(group_ids)],
        })

    def test_workplaces_and_additional_jobs_compute_summary_fields_and_validate_constraints(self):
        self.assertEqual(self.employee.all_site_names, "Bratislava centrum, Trnava prevádzka")
        self.assertEqual(self.employee.all_job_names, "Psychológ, Koordinátor")

        with self.assertRaises(ValidationError):
            self.employee.write({"main_site_id": self.site_terrain.id})

        with self.assertRaises(ValidationError):
            self.employee.write({"secondary_site_ids": [Command.set(self.site_main.ids)]})

    def test_salary_ranges_match_employee_experience_and_block_overlaps(self):
        primary_band = self.env["tenenet.hr.job.salary.range"].create({
            "job_id": self.job_primary.id,
            "level_name": "Výkon",
            "experience_years_from": 4.0,
            "experience_years_to": 6.0,
            "gross_min": 1300.0,
            "gross_max": 1600.0,
            "study_requirements": "Psychológia",
        })
        secondary_band = self.env["tenenet.hr.job.salary.range"].create({
            "job_id": self.job_secondary.id,
            "level_name": "Manažment",
            "experience_years_from": 3.0,
            "experience_years_to": 7.0,
            "gross_min": 1500.0,
            "gross_max": 1900.0,
            "notes": "Koordinačná rola",
        })

        self.employee.invalidate_recordset(["matched_salary_range_ids", "salary_guidance_html"])
        self.assertEqual(
            self.employee.matched_salary_range_ids,
            primary_band | secondary_band,
        )
        self.assertIn("Výkon", self.employee.salary_guidance_html)
        self.assertIn("Manažment", self.employee.salary_guidance_html)

        with self.assertRaises(ValidationError):
            self.env["tenenet.hr.job.salary.range"].create({
                "job_id": self.job_primary.id,
                "level_name": "výkon",
                "experience_years_from": 5.0,
                "experience_years_to": 8.0,
                "gross_min": 1600.0,
                "gross_max": 1800.0,
            })

    def test_employee_can_edit_own_bio_through_preferences(self):
        self.env["res.users"].with_user(self.employee_user).browse(self.employee_user.id).write({
            "bio": "Som odborník na poradenstvo a krízovú intervenciu.",
        })

        self.employee.invalidate_recordset(["bio"])
        self.assertEqual(
            self.employee.bio,
            "Som odborník na poradenstvo a krízovú intervenciu.",
        )

        with self.assertRaises(AccessError):
            self.env["res.users"].with_user(self.outsider_user).browse(self.employee_user.id).write({
                "bio": "Neoprávnená zmena",
            })

    def test_evaluation_access_follows_manager_and_visibility_rules(self):
        year = fields.Date.context_today(self).year
        visible_eval = self.env["tenenet.employee.evaluation"].with_user(self.manager_user).create({
            "employee_id": self.employee.id,
            "year": year,
            "summary": "Viditeľné hodnotenie",
            "visible_to_employee": True,
        })
        hidden_eval = self.env["tenenet.employee.evaluation"].with_user(self.hr_manager_user).create({
            "employee_id": self.employee.id,
            "year": year - 1,
            "summary": "Interné hodnotenie",
            "visible_to_employee": False,
        })

        employee_visible = self.env["tenenet.employee.evaluation"].with_user(self.employee_user).search([
            ("employee_id", "=", self.employee.id),
        ])
        public_employee = self.env["hr.employee.public"].with_user(self.employee_user).browse(self.employee.id)

        self.assertEqual(employee_visible, visible_eval)
        self.assertEqual(public_employee.evaluation_ids, visible_eval)
        self.assertEqual(public_employee.evaluation_ids.manager_name, self.manager.name)

        hidden_eval.with_user(self.manager_user).write({"summary": "Upravené interné hodnotenie"})
        self.assertEqual(hidden_eval.summary, "Upravené interné hodnotenie")

        with self.assertRaises(AccessError):
            self.env["tenenet.employee.evaluation"].with_user(self.outsider_user).create({
                "employee_id": self.employee.id,
                "year": year + 1,
                "summary": "Neoprávnený záznam",
            })
