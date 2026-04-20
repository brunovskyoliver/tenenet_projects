from datetime import timedelta

from lxml import etree

from odoo import Command, fields
from odoo.addons.mail.tools.discuss import Store
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetEmployeeProfileRework(TransactionCase):
    def setUp(self):
        super().setUp()
        self.base_user_group = self.env.ref("base.group_user")
        self.hr_manager_group = self.env.ref("hr.group_hr_manager")
        self.tenenet_manager_group = self.env.ref("tenenet_projects.group_tenenet_manager")

        self.manager_user = self._create_user("profile.manager", [self.base_user_group.id])
        self.employee_user = self._create_user("profile.employee", [self.base_user_group.id])
        self.outsider_user = self._create_user("profile.outsider", [self.base_user_group.id])
        self.hr_manager_user = self._create_user("profile.hr.manager", [self.hr_manager_group.id])
        self.tenenet_manager_user = self._create_user(
            "profile.tenenet.manager",
            [self.base_user_group.id, self.tenenet_manager_group.id],
        )

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
        self.weekly_schedule = self.env["tenenet.employee.weekly.workplace"].create({
            "employee_id": self.employee.id,
            "weekday": "6",
            "time_from": 8.0,
            "time_to": 12.0,
            "site_id": self.site_main.id,
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

    def test_missing_legal_context_is_reported_and_legacy_model_is_removed(self):
        self.assertNotIn("tenenet.hr.job.salary.range", self.env.registry.models)
        self.employee.invalidate_recordset(["salary_guidance_context_html", "salary_guidance_html"])
        self.assertIn("Aktívne priradenia", self.employee.salary_guidance_context_html)
        self.assertIn("nie je dostupný právny mzdový kontext", self.employee.salary_guidance_html)
        self.assertIn("Žiadny program", self.employee.salary_guidance_context_html)

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
        visible_eval = self.env["tenenet.employee.evaluation"].with_user(self.hr_manager_user).create({
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
        self.assertEqual(employee_visible, visible_eval)
        self.assertEqual(employee_visible.manager_name, self.manager.name)

        with self.assertRaises(UserError):
            hidden_eval.with_user(self.manager_user).write({"summary": "Upravené interné hodnotenie"})

        with self.assertRaises(UserError):
            self.env["tenenet.employee.evaluation"].with_user(self.outsider_user).create({
                "employee_id": self.employee.id,
                "year": year + 1,
                "summary": "Neoprávnený záznam",
            })

    def test_owner_can_write_only_self_service_employee_fields(self):
        owner_employee = self.env["hr.employee"].with_user(self.employee_user).browse(self.employee.id)
        owner_employee.write({
            "bio": "Aktualizované bio",
            "additional_note": "Poznámka k práci",
        })
        self.employee.invalidate_recordset(["bio", "additional_note"])
        self.assertEqual(self.employee.bio, "Aktualizované bio")
        self.assertEqual(self.employee.additional_note, "Poznámka k práci")
        self.assertEqual(owner_employee.read(["additional_note"])[0]["additional_note"], "Poznámka k práci")
        self.assertEqual(
            self.env["hr.employee"].with_user(self.manager_user).browse(self.employee.id).read(["additional_note"])[0]["additional_note"],
            "Poznámka k práci",
        )
        protected_private_form_fields = [
            field
            for field in [
                "current_leave_id",
                "current_leave_state",
                "leave_date_from",
                "allocation_count",
            ]
            if field in owner_employee._fields
        ]
        if protected_private_form_fields:
            owner_values = owner_employee.read(protected_private_form_fields)[0]
            manager_values = self.env["hr.employee"].with_user(self.manager_user).browse(self.employee.id).read(
                protected_private_form_fields
            )[0]
            for field in protected_private_form_fields:
                self.assertIn(field, owner_values)
                self.assertIn(field, manager_values)

        with self.assertRaises(UserError):
            owner_employee.write({"main_site_id": self.site_secondary.id})

        with self.assertRaises(UserError):
            owner_employee.write({"secondary_site_ids": [Command.clear()]})

        with self.assertRaises(UserError):
            self.env["hr.employee"].with_user(self.manager_user).browse(self.employee.id).write({
                "bio": "Manažér nemôže upravovať",
            })

        with self.assertRaises(AccessError):
            self.env["hr.employee"].with_user(self.tenenet_manager_user).browse(self.employee.id).read(["name"])

        with self.assertRaises(AccessError):
            self.env["hr.employee"].with_user(self.outsider_user).browse(self.employee.id).read(["additional_note"])

    def test_public_card_can_open_private_card_for_owner_higher_up_and_hr_admin(self):
        public_owner = self.env["hr.employee.public"].with_user(self.employee_user).browse(self.employee.id)
        self.assertTrue(public_owner.tenenet_can_open_private_employee_card)
        owner_action = public_owner.action_tenenet_open_private_employee_card()
        self.assertEqual(owner_action["res_model"], "hr.employee")
        self.assertEqual(owner_action["res_id"], self.employee.id)
        self.assertEqual(owner_action["view_mode"], "form")
        self.assertEqual(owner_action["views"][0], (self.env.ref("hr.view_employee_form").id, "form"))
        self.assertEqual(public_owner.get_formview_action()["res_model"], "hr.employee")
        self.assertEqual(public_owner.action_tenenet_open_employee_card()["res_model"], "hr.employee")

        public_higher_up = self.env["hr.employee.public"].with_user(self.manager_user).browse(self.employee.id)
        self.assertTrue(public_higher_up.tenenet_can_open_private_employee_card)
        higher_up_action = public_higher_up.action_tenenet_open_private_employee_card()
        self.assertEqual(higher_up_action["res_model"], "hr.employee")
        self.assertEqual(higher_up_action["res_id"], self.employee.id)
        self.assertEqual(public_higher_up.action_tenenet_open_employee_card()["res_model"], "hr.employee")

        public_hr_admin = self.env["hr.employee.public"].with_user(self.hr_manager_user).browse(self.employee.id)
        self.assertTrue(public_hr_admin.tenenet_can_open_private_employee_card)
        hr_action = public_hr_admin.action_tenenet_open_private_employee_card()
        self.assertEqual(hr_action["res_model"], "hr.employee")
        self.assertEqual(hr_action["res_id"], self.employee.id)
        self.assertEqual(public_hr_admin.action_tenenet_open_employee_card()["res_model"], "hr.employee")

        public_outsider = self.env["hr.employee.public"].with_user(self.outsider_user).browse(self.employee.id)
        self.assertFalse(public_outsider.tenenet_can_open_private_employee_card)
        public_action = public_outsider.action_tenenet_open_employee_card()
        self.assertEqual(public_action["res_model"], "hr.employee.public")
        self.assertEqual(public_action["res_id"], self.employee.id)
        with self.assertRaises(UserError):
            public_outsider.action_tenenet_open_private_employee_card()

    def test_project_manager_can_open_employee_cards_for_current_project_assignments(self):
        admin_program = self.env["tenenet.program"].with_context(active_test=False).search([
            ("code", "=", "ADMIN_TENENET"),
        ], limit=1)
        pm_user = self._create_user("profile.project.manager", [self.base_user_group.id])
        pm_employee = self.env["hr.employee"].create({
            "name": "Projektový manažér",
            "user_id": pm_user.id,
        })
        project = self.env["tenenet.project"].create({
            "name": "Projekt pre kartu PM",
            "program_ids": [Command.set(admin_program.ids)],
            "project_manager_id": pm_employee.id,
        })
        assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": project.id,
            "allocation_ratio": 50.0,
            "wage_hm": 12.0,
        })
        asset_type = self.env["tenenet.employee.asset.type"].create({"name": "Notebook PM karta"})
        asset = self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": asset_type.id,
            "serial_number": "PM-CARD-001",
        })
        training = self.env["tenenet.employee.training"].create({
            "employee_id": self.employee.id,
            "name": "PM čítanie školenia",
        })
        evaluation = self.env["tenenet.employee.evaluation"].with_user(self.hr_manager_user).create({
            "employee_id": self.employee.id,
            "year": fields.Date.context_today(self.employee).year,
            "summary": "Interné hodnotenie pre PM",
            "visible_to_employee": False,
        })
        wage_override = self.env["tenenet.employee.wage.override"].with_user(self.hr_manager_user).create({
            "employee_id": self.employee.id,
            "job_id": self.job_primary.id,
            "amount_override": 1250.0,
        })

        self.employee.invalidate_recordset(["tenenet_project_manager_user_ids"])
        self.assertIn(pm_user, self.employee.tenenet_project_manager_user_ids)
        self.env.cr.execute(
            """
            DELETE FROM hr_employee_tenenet_project_manager_user_rel
             WHERE employee_id = %s AND user_id = %s
            """,
            [self.employee.id, pm_user.id],
        )
        self.employee.invalidate_recordset(["tenenet_project_manager_user_ids"])
        self.assertNotIn(pm_user, self.employee.tenenet_project_manager_user_ids)
        self.assertEqual(
            self.env["hr.employee"].with_user(pm_user).search_count([("id", "=", self.employee.id)]),
            1,
        )

        public_employee = self.env["hr.employee.public"].with_user(pm_user).browse(self.employee.id)
        self.assertTrue(public_employee.tenenet_can_open_private_employee_card)
        action = public_employee.action_tenenet_open_private_employee_card()
        self.assertEqual(action["res_model"], "hr.employee")
        self.assertEqual(action["res_id"], self.employee.id)

        assignment_action = assignment.with_user(pm_user).action_open_employee_card_readonly()
        self.assertEqual(assignment_action["res_model"], "hr.employee")
        self.assertEqual(assignment_action["res_id"], self.employee.id)

        pm_employee_card = self.env["hr.employee"].with_user(pm_user).browse(self.employee.id)
        self.assertTrue(pm_employee_card.tenenet_is_project_manager_viewer)
        values = pm_employee_card.read([
            "name",
            "private_phone",
            "assignment_ids",
            "asset_ids",
            "training_ids",
            "wage_override_ids",
        ])[0]
        self.assertEqual(values["assignment_ids"], assignment.ids)
        self.assertEqual(values["asset_ids"], asset.ids)
        self.assertEqual(values["training_ids"], training.ids)
        self.assertEqual(values["wage_override_ids"], wage_override.ids)
        self.assertEqual(evaluation.with_user(pm_user).read(["summary"])[0]["summary"], "Interné hodnotenie pre PM")

        arch = pm_employee_card.get_view(self.env.ref("hr.view_employee_form").id, "form")["arch"]
        root = etree.fromstring(arch.encode())
        page_names = {
            page.get("name")
            for page in root.xpath("//page")
            if page.get("name")
        }
        self.assertTrue({"personal_information", "payroll_information", "hr_settings"}.issubset(page_names))
        private_email_field = root.xpath("//page[@name='personal_information']//field[@name='private_email']")[0]
        self.assertEqual(private_email_field.get("readonly"), "1")

        with self.assertRaises(UserError):
            pm_employee_card.write({"bio": "PM nemôže upravovať kartu"})

    def test_project_manager_employee_card_access_requires_current_assignment(self):
        admin_program = self.env["tenenet.program"].with_context(active_test=False).search([
            ("code", "=", "ADMIN_TENENET"),
        ], limit=1)
        pm_user = self._create_user("profile.project.manager.scope", [self.base_user_group.id])
        pm_employee = self.env["hr.employee"].create({
            "name": "PM rozsah karty",
            "user_id": pm_user.id,
        })
        today = fields.Date.context_today(self.employee)
        future_employee = self.env["hr.employee"].create({"name": "Budúci zamestnanec projektu"})
        finished_employee = self.env["hr.employee"].create({"name": "Ukončený zamestnanec projektu"})
        inactive_employee = self.env["hr.employee"].create({"name": "Neaktívny zamestnanec projektu"})
        inactive_project_employee = self.env["hr.employee"].create({"name": "Zamestnanec neaktívneho projektu"})
        unrelated_employee = self.env["hr.employee"].create({"name": "Cudzí zamestnanec projektu"})
        project = self.env["tenenet.project"].create({
            "name": "Projekt PM rozsah",
            "program_ids": [Command.set(admin_program.ids)],
            "project_manager_id": pm_employee.id,
        })
        inactive_project = self.env["tenenet.project"].create({
            "name": "Neaktívny projekt PM rozsah",
            "program_ids": [Command.set(admin_program.ids)],
            "project_manager_id": pm_employee.id,
            "active": False,
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": future_employee.id,
            "project_id": project.id,
            "date_start": today + timedelta(days=30),
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": finished_employee.id,
            "project_id": project.id,
            "date_end": today - timedelta(days=1),
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": inactive_employee.id,
            "project_id": project.id,
            "active": False,
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": inactive_project_employee.id,
            "project_id": inactive_project.id,
        })

        employee_model = self.env["hr.employee"].with_user(pm_user)
        for employee in (
            future_employee,
            finished_employee,
            inactive_employee,
            inactive_project_employee,
            unrelated_employee,
        ):
            self.assertEqual(employee_model.search_count([("id", "=", employee.id)]), 0)

    def test_owner_and_higher_up_private_form_includes_readonly_private_tabs(self):
        expected_private_pages = {"personal_information", "payroll_information", "hr_settings"}

        for user in (self.employee_user, self.manager_user):
            employee = self.env["hr.employee"].with_user(user).browse(self.employee.id)
            arch = employee.get_view(self.env.ref("hr.view_employee_form").id, "form")["arch"]
            root = etree.fromstring(arch.encode())
            page_names = {
                page.get("name")
                for page in root.xpath("//page")
                if page.get("name")
            }
            self.assertTrue(expected_private_pages.issubset(page_names))

            private_email_field = root.xpath("//page[@name='personal_information']//field[@name='private_email']")[0]
            self.assertEqual(private_email_field.get("readonly"), "1")

            settings_fields = root.xpath("//page[@name='hr_settings']//field")
            self.assertTrue(settings_fields)
            self.assertTrue(all(field.get("readonly") == "1" for field in settings_fields))

            self.assertFalse(root.xpath("//page[@name='personal_information']//button"))
            self.assertFalse(root.xpath("//page[@name='payroll_information']//button"))
            self.assertFalse(root.xpath("//page[@name='hr_settings']//button"))
            self.assertTrue(root.xpath("//button[@name='action_tenenet_open_employee_update_request_wizard']"))
            self.assertTrue(root.xpath("//field[@name='current_employee_skill_ids'][@readonly='not can_manage_services']"))
            self.assertTrue(root.xpath("//field[@name='job_title'][@readonly='not can_manage_services']"))
            self.assertTrue(root.xpath("//field[@name='organizational_unit_id'][@readonly='not can_manage_services']"))
            self.assertTrue(root.xpath("//field[@name='additional_job_ids'][@readonly='not can_manage_services']"))

    def test_public_form_uses_tenenet_workplaces_and_public_resume_only(self):
        public_employee = self.env["hr.employee.public"].with_user(self.outsider_user).browse(self.employee.id)
        arch = public_employee.get_view(self.env.ref("hr.hr_employee_public_view_form").id, "form")["arch"]
        root = etree.fromstring(arch.encode())

        self.assertFalse(root.xpath("//field[@name='work_location_id']"))
        self.assertTrue(root.xpath("//field[@name='main_site_id'][@string='Pracovisko']"))
        self.assertTrue(root.xpath("//field[@name='weekly_workplace_ids']"))
        self.assertTrue(root.xpath("//page[@name='resume']//field[@name='bio']"))
        self.assertTrue(root.xpath("//page[@name='resume']//field[@name='current_employee_skill_ids']"))
        self.assertFalse(root.xpath("//page[@name='resume']//field[@name='resume_line_ids']"))
        self.assertFalse(root.xpath("//page[@name='resume']//field[@name='evaluation_ids']"))
        self.assertFalse(root.xpath("//page[@name='certification']"))

        self.assertEqual(public_employee.main_site_id, self.employee.main_site_id)
        self.assertEqual(public_employee.weekly_workplace_ids, self.weekly_schedule)

    def test_work_form_replaces_usual_work_location_with_weekly_schedule(self):
        employee = self.env["hr.employee"].with_user(self.employee_user).browse(self.employee.id)
        arch = employee.get_view(self.env.ref("hr.view_employee_form").id, "form")["arch"]
        root = etree.fromstring(arch.encode())

        self.assertTrue(root.xpath("//separator[@string='Týždenný rozvrh pracovísk']"))
        self.assertTrue(root.xpath("//field[@name='weekly_workplace_ids']"))
        self.assertFalse(root.xpath("//group[@string='Usual Work Location']"))

    def test_base_only_owner_can_read_private_card_related_tabs(self):
        admin_program = self.env["tenenet.program"].with_context(active_test=False).search([
            ("code", "=", "ADMIN_TENENET"),
        ], limit=1)
        project = self.env["tenenet.project"].create({
            "name": "Projekt karta zamestnanca",
            "program_ids": [Command.set(admin_program.ids)],
            "site_ids": [Command.set([self.site_main.id])],
        })
        assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": project.id,
            "allocation_ratio": 50.0,
            "wage_hm": 12.0,
        })
        asset_type = self.env["tenenet.employee.asset.type"].create({"name": "Notebook karta"})
        asset = self.env["tenenet.employee.asset"].create({
            "employee_id": self.employee.id,
            "asset_type_id": asset_type.id,
            "serial_number": "CARD-OWNER-001",
            "cost": 900.0,
        })
        site_key = self.env["tenenet.employee.site.key"].create({
            "employee_id": self.employee.id,
            "site_id": self.site_main.id,
        })
        training = self.env["tenenet.employee.training"].create({
            "employee_id": self.employee.id,
            "name": "Bezpečnosť práce",
        })
        wage_override = self.env["tenenet.employee.wage.override"].with_user(self.hr_manager_user).create({
            "employee_id": self.employee.id,
            "job_id": self.job_primary.id,
            "amount_override": 1200.0,
            "notes": "Individuálna výnimka",
        })
        activity = self.env["mail.activity"].create({
            "res_model_id": self.env["ir.model"]._get_id("hr.employee"),
            "res_id": self.employee.id,
            "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
            "summary": "Skontrolovať kartu",
            "user_id": self.hr_manager_user.id,
            "date_deadline": fields.Date.context_today(self.employee),
        })

        owner_employee = self.env["hr.employee"].with_user(self.employee_user).browse(self.employee.id)
        self.assertEqual(owner_employee.activity_ids, activity)
        self.assertTrue(owner_employee.message_ids)
        homeworking_fields = [
            field_name
            for field_name in ("work_location_name", "work_location_type")
            if field_name in owner_employee._fields
        ]
        values = owner_employee.read([
            "name",
            "organizational_unit_id",
            "main_site_id",
            "secondary_site_ids",
            "additional_note",
            "assignment_ids",
            "asset_ids",
            "site_key_ids",
            "training_ids",
            "wage_override_ids",
            "salary_guidance_context_html",
            "salary_guidance_html",
            *homeworking_fields,
        ])[0]
        self.assertEqual(values["main_site_id"][0], self.site_main.id)
        self.assertEqual(values["secondary_site_ids"], self.site_secondary.ids)
        self.assertEqual(values["assignment_ids"], assignment.ids)
        self.assertEqual(values["asset_ids"], asset.ids)
        self.assertEqual(values["site_key_ids"], site_key.ids)
        self.assertEqual(values["training_ids"], training.ids)
        self.assertEqual(values["wage_override_ids"], wage_override.ids)
        self.assertIn("1 aktívnych výnimiek", values["salary_guidance_context_html"])
        self.assertIn("o_tenenet_salary_guidance", values["salary_guidance_html"])
        for field_name in homeworking_fields:
            self.assertIn(field_name, values)

        protected_web_spec = {
            "name": {},
            "can_manage_services": {},
            "tenenet_can_edit_self_employee_fields": {},
        }
        protected_web_spec.update({
            field_name: field_spec
            for field_name, field_spec in {
                "current_leave_id": {"fields": {"display_name": {}}},
                "current_leave_state": {},
                "leave_date_from": {},
                "allocation_count": {},
                "work_location_name": {},
                "work_location_type": {},
                "activity_ids": {
                    "fields": {
                        "activity_type_id": {"fields": {"display_name": {}}},
                        "summary": {},
                        "date_deadline": {},
                        "user_id": {"fields": {"display_name": {}}},
                    },
                },
                "activity_state": {},
                "activity_exception_decoration": {},
                "activity_exception_icon": {},
                "activity_type_id": {"fields": {"display_name": {}}},
                "activity_type_icon": {},
                "activity_user_id": {"fields": {"display_name": {}}},
                "activity_date_deadline": {},
                "my_activity_date_deadline": {},
                "activity_summary": {},
                "message_ids": {"fields": {"display_name": {}}},
                "message_follower_ids": {"fields": {"display_name": {}}},
                "message_partner_ids": {"fields": {"display_name": {}}},
                "message_needaction_counter": {},
                "message_attachment_count": {},
            }.items()
            if field_name in owner_employee._fields
        })
        web_values = owner_employee.web_read(protected_web_spec)[0]
        self.assertFalse(web_values["can_manage_services"])
        self.assertTrue(web_values["tenenet_can_edit_self_employee_fields"])
        for field_name in protected_web_spec:
            self.assertIn(field_name, web_values)

        store = Store(owner_employee.env.user.partner_id)
        owner_employee._thread_to_store(
            store,
            [],
            request_list=[
                "activities",
                "attachments",
                "contact_fields",
                "followers",
                "scheduledMessages",
                "suggestedRecipients",
            ],
        )
        thread_values = next(
            record
            for record in store.get_result()["mail.thread"]
            if record["id"] == self.employee.id and record["model"] == "hr.employee"
        )
        self.assertEqual(thread_values["activities"], activity.ids)

        self.assertEqual(
            assignment.with_user(self.employee_user).read([
                "project_id",
                "allocation_ratio",
                "date_start",
                "date_end",
                "wage_hm",
                "wage_ccp",
            ])[0]["project_id"][0],
            project.id,
        )
        self.assertEqual(
            asset.with_user(self.employee_user).read([
                "asset_type_id",
                "serial_number",
                "handover_date",
                "currency_id",
                "cost",
                "sign_state",
                "sign_request_id",
                "note",
                "active",
            ])[0]["asset_type_id"][0],
            asset_type.id,
        )
        self.assertEqual(
            site_key.with_user(self.employee_user).read(["site_id", "active"])[0]["site_id"][0],
            self.site_main.id,
        )
        self.assertEqual(
            training.with_user(self.employee_user).read([
                "name",
                "training_type",
                "provider",
                "date_from",
                "date_to",
                "certificate_date",
                "active",
            ])[0]["name"],
            "Bezpečnosť práce",
        )
        self.assertEqual(
            wage_override.with_user(self.employee_user).read([
                "job_id",
                "amount_override",
                "notes",
            ])[0]["notes"],
            "Individuálna výnimka",
        )

        manager_employee = self.env["hr.employee"].with_user(self.manager_user).browse(self.employee.id)
        self.assertEqual(manager_employee.read(["assignment_ids"])[0]["assignment_ids"], assignment.ids)
        self.assertEqual(manager_employee.read(["wage_override_ids"])[0]["wage_override_ids"], wage_override.ids)
        self.assertFalse(
            self.env["tenenet.project.assignment"].with_user(self.outsider_user).search([
                ("employee_id", "=", self.employee.id),
            ])
        )

        with self.assertRaises(AccessError):
            asset.with_user(self.employee_user).write({"note": "Zamestnanec neupravuje majetok"})
        with self.assertRaises(AccessError):
            wage_override.with_user(self.employee_user).write({"notes": "Zamestnanec neupravuje mzdové výnimky"})
        with self.assertRaises(AccessError):
            wage_override.with_user(self.outsider_user).read(["notes"])

    def test_weekly_workplace_owner_permissions_and_validation(self):
        Schedule = self.env["tenenet.employee.weekly.workplace"]
        schedule = Schedule.with_user(self.employee_user).create({
            "employee_id": self.employee.id,
            "weekday": "0",
            "time_from": 8.0,
            "time_to": 12.0,
            "site_id": self.site_main.id,
        })
        schedule.with_user(self.employee_user).write({"time_to": 13.0})
        self.assertEqual(schedule.time_to, 13.0)

        with self.assertRaises(UserError):
            schedule.with_user(self.manager_user).write({"time_to": 14.0})

        before_count = Schedule.search_count([])
        with self.assertRaises(UserError):
            Schedule.with_user(self.manager_user).create({
                "employee_id": self.employee.id,
                "weekday": "3",
                "time_from": 8.0,
                "time_to": 12.0,
                "site_id": self.site_main.id,
            })
        self.assertEqual(Schedule.search_count([]), before_count)

        with self.assertRaises(ValidationError):
            Schedule.with_user(self.employee_user).create({
                "employee_id": self.employee.id,
                "weekday": "0",
                "time_from": 12.5,
                "time_to": 14.0,
                "site_id": self.site_secondary.id,
            })

        with self.assertRaises(ValidationError):
            Schedule.with_user(self.employee_user).create({
                "employee_id": self.employee.id,
                "weekday": "1",
                "time_from": 10.0,
                "time_to": 9.0,
                "site_id": self.site_main.id,
            })

        with self.assertRaises(ValidationError):
            Schedule.with_user(self.employee_user).create({
                "employee_id": self.employee.id,
                "weekday": "2",
                "time_from": 8.0,
                "time_to": 10.0,
                "site_id": self.site_terrain.id,
            })

    def test_services_and_skills_are_not_self_or_higher_up_editable(self):
        service = self.env["tenenet.employee.service"].with_user(self.hr_manager_user).create({
            "employee_id": self.employee.id,
            "name": "Poradenstvo",
        })
        with self.assertRaises(UserError):
            service.with_user(self.manager_user).write({"name": "Manažérska zmena"})
        with self.assertRaises(UserError):
            service.with_user(self.employee_user).write({"name": "Vlastná zmena"})

        skill_type = self.env["hr.skill.type"].create({"name": "Jazyky"})
        skill = self.env["hr.skill"].create({
            "name": "Angličtina",
            "skill_type_id": skill_type.id,
        })
        level = self.env["hr.skill.level"].create({
            "name": "B2",
            "skill_type_id": skill_type.id,
            "level_progress": 80,
        })
        employee_skill = self.env["hr.employee.skill"].with_user(self.hr_manager_user).create({
            "employee_id": self.employee.id,
            "skill_type_id": skill_type.id,
            "skill_id": skill.id,
            "skill_level_id": level.id,
        })
        with self.assertRaises(UserError):
            employee_skill.with_user(self.employee_user).write({"skill_level_id": level.id})

    def test_public_profile_exposes_allowed_readonly_profile_parts(self):
        public_employee = self.env["hr.employee.public"].with_user(self.employee_user).browse(self.employee.id)
        self.assertEqual(public_employee.bio, self.employee.bio)
        self.assertEqual(public_employee.service_ids, self.employee.service_ids)
        self.assertEqual(public_employee.weekly_workplace_ids, self.employee.weekly_workplace_ids)
        self.assertEqual(public_employee.all_site_names, self.employee.all_site_names)
        self.assertNotIn("additional_note", public_employee._fields)
        self.assertNotIn("evaluation_ids", public_employee._fields)

    def test_update_request_button_and_wizard_are_placeholders(self):
        owner_employee = self.env["hr.employee"].with_user(self.employee_user).browse(self.employee.id)
        button_action = owner_employee.action_tenenet_open_employee_update_request_wizard()
        self.assertEqual(button_action["type"], "ir.actions.client")
        self.assertEqual(button_action["tag"], "display_notification")
        self.assertFalse(self.env["helpdesk.ticket"].sudo().search_count([
            ("tenenet_requested_by_user_id", "=", self.employee_user.id),
        ]))

        wizard = self.env["tenenet.employee.update.request.wizard"].with_user(self.employee_user).create({
            "employee_id": self.employee.id,
            "request_text": "Prosím aktualizovať telefónne číslo.",
        })
        wizard_action = wizard.action_confirm()
        self.assertEqual(wizard_action["type"], "ir.actions.client")
        self.assertEqual(wizard_action["tag"], "display_notification")
        self.assertFalse(self.env["helpdesk.ticket"].sudo().search_count([
            ("tenenet_requested_by_user_id", "=", self.employee_user.id),
        ]))

        with self.assertRaises(AccessError):
            self.env["tenenet.employee.update.request.wizard"].with_user(self.employee_user).create({
                "employee_id": self.outsider.id,
                "request_text": "Cudzia karta",
            }).action_confirm()
