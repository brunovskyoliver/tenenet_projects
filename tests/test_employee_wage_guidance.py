from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetEmployeeWageGuidance(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env["tenenet.program"]._sync_default_wage_regimes()

        self.program_spodask = self.env.ref("tenenet_projects.tenenet_program_spodask")
        self.program_scpp = self.env.ref("tenenet_projects.tenenet_program_scpp")
        self.program_avl = self.env.ref("tenenet_projects.tenenet_program_avl")
        self.program_psc_sc = self.env.ref("tenenet_projects.tenenet_program_psc_sc")

        self.job_psycholog = self.env["hr.job"].create({"name": "Psychológ"})
        self.job_socialny_pracovnik = self.env["hr.job"].create({"name": "Sociálny pracovník"})
        self.job_specialny_pedagog = self.env["hr.job"].create({"name": "Špeciálny pedagóg"})

        self.employee = self.env["hr.employee"].create({
            "name": "Test Zamestnanec",
            "job_id": self.job_socialny_pracovnik.id,
            "experience_years_total": 8.5,
            "monthly_gross_salary_target": 800.0,
        })

    def test_public_interest_guidance_uses_table_and_employee_override(self):
        self.env["tenenet.hr.job.legal.wage.map"].create({
            "job_id": self.job_socialny_pracovnik.id,
            "regime": "law_553_public_interest",
            "pay_class": 7,
        })
        self.employee.write({"wage_program_override_id": self.program_spodask.id})

        self.employee.invalidate_recordset(["salary_guidance_html"])
        self.assertIn("751.00 EUR", self.employee.salary_guidance_html)
        self.assertIn("SPODaSK", self.employee.salary_guidance_html)

        self.env["tenenet.employee.wage.override"].create({
            "employee_id": self.employee.id,
            "program_id": self.program_spodask.id,
            "pay_class": 8,
            "notes": "Vyššia trieda podľa interného zaradenia.",
        })

        self.employee.invalidate_recordset(["salary_guidance_html"])
        self.assertIn("830.50 EUR", self.employee.salary_guidance_html)
        self.assertIn("Override", self.employee.salary_guidance_html)

    def test_pedagogical_guidance_uses_pedagogical_table(self):
        self.employee.write({
            "job_id": self.job_specialny_pedagog.id,
            "wage_program_override_id": self.program_scpp.id,
            "experience_years_total": 3.0,
        })
        self.env["tenenet.hr.job.legal.wage.map"].create({
            "job_id": self.job_specialny_pedagog.id,
            "regime": "law_553_pedagogical",
            "pay_class": 7,
            "work_class": 2,
        })

        self.employee.invalidate_recordset(["salary_guidance_html"])
        self.assertIn("1 519.00 EUR", self.employee.salary_guidance_html)
        self.assertIn("PrT 2", self.employee.salary_guidance_html)

    def test_healthcare_guidance_uses_summary_table_and_lane_override(self):
        self.employee.write({
            "job_id": self.job_psycholog.id,
            "wage_program_override_id": self.program_avl.id,
            "experience_years_total": 1.4,
        })
        self.env["tenenet.hr.job.legal.wage.map"].create({
            "job_id": self.job_psycholog.id,
            "regime": "healthcare",
            "healthcare_profession_code": "psychologist",
            "qualification_lane": "professional",
        })

        self.employee.invalidate_recordset(["salary_guidance_html"])
        self.assertIn("1 828.80 EUR", self.employee.salary_guidance_html)

        self.env["tenenet.employee.wage.override"].create({
            "employee_id": self.employee.id,
            "program_id": self.program_avl.id,
            "qualification_lane": "specialized",
            "notes": "Špecializované činnosti.",
        })
        self.employee.invalidate_recordset(["salary_guidance_html"])
        self.assertIn("2 148.84 EUR", self.employee.salary_guidance_html)

    def test_assignment_program_context_used_when_no_employee_override(self):
        self.employee.write({
            "job_id": self.job_psycholog.id,
            "wage_program_override_id": False,
            "experience_years_total": 2.0,
        })
        self.env["tenenet.hr.job.legal.wage.map"].create({
            "job_id": self.job_psycholog.id,
            "regime": "healthcare",
            "healthcare_profession_code": "psychologist",
            "qualification_lane": "professional",
        })
        project = self.env["tenenet.project"].create({
            "name": "Psychiatrické služby",
            "program_ids": [Command.set(self.program_psc_sc.ids)],
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": project.id,
            "program_id": self.program_psc_sc.id,
        })

        self.employee.invalidate_recordset(["salary_guidance_html"])
        self.assertIn("PSC Senec", self.employee.salary_guidance_html)
        self.assertIn("1 844.04 EUR", self.employee.salary_guidance_html)

    def test_legacy_salary_bands_are_removed_and_legal_guidance_still_works(self):
        self.employee.write({
            "wage_program_override_id": self.program_spodask.id,
            "job_id": self.job_socialny_pracovnik.id,
            "experience_years_total": 5.0,
        })
        self.env["tenenet.hr.job.legal.wage.map"].create({
            "job_id": self.job_socialny_pracovnik.id,
            "regime": "law_553_public_interest",
            "pay_class": 4,
        })

        self.assertNotIn("tenenet.hr.job.salary.range", self.env.registry.models)
        self.employee.invalidate_recordset(["salary_guidance_html", "salary_guidance_context_html"])
        self.assertIn("595.50 EUR", self.employee.salary_guidance_html)
        self.assertIn("Manuálne zvolený program", self.employee.salary_guidance_context_html)
