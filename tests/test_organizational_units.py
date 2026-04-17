from pathlib import Path

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestOrganizationalUnits(TransactionCase):
    def setUp(self):
        super().setUp()
        self.unit_tenenet = self.env.ref("tenenet_projects.tenenet_organizational_unit_tenenet_oz")
        self.unit_scpp = self.env.ref("tenenet_projects.tenenet_organizational_unit_scpp")
        self.unit_kalia = self.env.ref("tenenet_projects.tenenet_organizational_unit_kalia")

    def test_program_stores_organizational_unit_and_project_inherits_it(self):
        program = self.env["tenenet.program"].create({
            "name": "Program test org",
            "code": "ORG_TEST",
            "organizational_unit_id": self.unit_scpp.id,
        })
        project = self.env["tenenet.project"].create({
            "name": "Projekt org",
            "program_ids": [(4, program.id)],
        })

        self.assertEqual(program.organizational_unit_id, self.unit_scpp)
        self.assertEqual(project.reporting_program_id, program)
        self.assertEqual(project.organizational_unit_id, self.unit_scpp)

    def test_project_organizational_unit_override_wins_and_can_fallback(self):
        program = self.env["tenenet.program"].create({
            "name": "Program override org",
            "code": "ORG_OVERRIDE",
            "organizational_unit_id": self.unit_scpp.id,
        })
        project = self.env["tenenet.project"].create({
            "name": "Projekt org override",
            "program_ids": [(4, program.id)],
            "organizational_unit_override_id": self.unit_kalia.id,
        })

        self.assertEqual(project.organizational_unit_id, self.unit_kalia)

        project.write({"organizational_unit_override_id": False})

        self.assertEqual(project.organizational_unit_id, self.unit_scpp)

    def test_employee_requires_organizational_unit_when_active(self):
        with self.assertRaises(ValidationError):
            self.env["hr.employee"].create({
                "name": "Bez zložky",
                "organizational_unit_id": False,
            })

    def test_contract_position_is_stored_but_not_rendered_in_employee_view(self):
        employee = self.env["hr.employee"].create({
            "name": "Zmluvná pozícia",
            "contract_position": "Pozícia podľa zmluvy",
            "organizational_unit_id": self.unit_tenenet.id,
        })

        self.assertEqual(employee.contract_position, "Pozícia podľa zmluvy")
        employee_view_path = Path(__file__).resolve().parents[1] / "views" / "hr_employee_views.xml"
        self.assertNotIn("contract_position", employee_view_path.read_text(encoding="utf-8"))

    def test_program_constraint_blocks_active_program_without_unit(self):
        program = self.env["tenenet.program"].create({
            "name": "Dočasný program",
            "code": "TMP_ORG",
        })
        with self.assertRaises(ValidationError):
            program.write({"organizational_unit_id": False})
