from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestResUsersLang(TransactionCase):
    def _expected_lang(self):
        installed_codes = {code for code, _name in self.env["res.lang"].get_installed()}
        return "sk_SK" if "sk_SK" in installed_codes else self.env.lang

    def test_res_users_default_get_prefills_slovak_lang(self):
        defaults = self.env["res.users"].default_get(["lang"])

        self.assertEqual(defaults.get("lang"), self._expected_lang())

    def test_res_users_create_defaults_lang_to_slovak(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Lang Default",
            "login": "lang.default@example.com",
            "email": "lang.default@example.com",
        })

        self.assertEqual(user.lang, self._expected_lang())

    def test_hr_employee_action_create_user_sets_slovak_lang_default(self):
        employee = self.env["hr.employee"].create({
            "name": "Create User Employee",
            "work_email": "employee.lang@example.com",
        })

        action = employee.action_create_user()

        self.assertEqual(action["res_model"], "res.users")
        self.assertEqual(action["context"].get("default_lang"), self._expected_lang())
