import csv
import importlib.util
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from odoo.tests import TransactionCase, tagged


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


@tagged("post_install", "-at_install")
class TestEmployeeImportScripts(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        scripts_dir = Path(__file__).resolve().parents[1] / "scripts"
        cls.cleanup_script = _load_module(
            "tenenet_generate_employee_cleanup",
            scripts_dir / "generate_employee_cleanup_from_xlsx.py",
        )
        cls.import_script = _load_module(
            "tenenet_import_ready_employees",
            scripts_dir / "import_ready_employees_from_csv.py",
        )

    def test_cleanup_rows_map_org_units_and_reports_location_and_skip(self):
        rows = [
            {
                "__row__": 10,
                "Zamestnávateľ": "SCPaP",
                "Titul": "Mgr.",
                "Priezvisko a meno": "Testovacia Logopedička",
                "Program,do ktorého patria": "SCPaP",
                "Pozícia podľa pracovnej zmluvy": "logopéd",
                "Pozícia": "logopéd",
                "Priamy nadriadený": "",
                "Lokácia": "Senec, BSK, TTSK",
                "Email": "test.logoped@tenenet.sk",
                "TEL": "910,549,005",
            },
            {
                "__row__": 11,
                "Zamestnávateľ": "Tenenet",
                "Titul": "",
                "Priezvisko a meno": "Skip Osoba",
                "Program,do ktorého patria": "nedávať",
                "Pozícia podľa pracovnej zmluvy": "recepčná",
                "Pozícia": "recepčná",
                "Priamy nadriadený": "",
                "Lokácia": "Senec",
                "Email": "",
                "TEL": "",
            },
            {
                "__row__": 12,
                "Zamestnávateľ": "Tenenet",
                "Titul": "",
                "Priezvisko a meno": "Web Osoba",
                "Program,do ktorého patria": "už je na webe",
                "Pozícia podľa pracovnej zmluvy": "psychológ",
                "Pozícia": "psychológ",
                "Priamy nadriadený": "",
                "Lokácia": "Senec",
                "Email": "web@tenenet.sk",
                "TEL": "910549006",
            },
        ]

        cleaned_rows = self.cleanup_script.clean_rows(rows)
        scpap_row = next(row for row in cleaned_rows if row.name == "Testovacia Logopedička")
        skip_row = next(row for row in cleaned_rows if row.name == "Skip Osoba")
        web_row = next(row for row in cleaned_rows if row.name == "Web Osoba")

        self.assertEqual(scpap_row.org_unit_code, "SCPP")
        self.assertEqual(scpap_row.wage_program_code, "SCPAP")
        self.assertEqual(scpap_row.mobile_phone, "+421 910 549 005")
        self.assertEqual(scpap_row.main_site_name, "Senec")
        self.assertIn("BSK, TTSK", " | ".join(scpap_row.location_unresolved))

        self.assertEqual(skip_row.import_action, "skip")
        self.assertEqual(skip_row.skip_reason, "riadok označený `nedávať`")

        self.assertEqual(web_row.import_action, "import")
        self.assertFalse(web_row.wage_program_code)

        report = self.cleanup_script.build_missing_fields_report(cleaned_rows)
        self.assertIn("Neimportované riadky", report)
        self.assertIn("Skip Osoba", report)
        self.assertIn("Web Osoba", report)

    def test_import_ready_directory_updates_existing_employee(self):
        org_unit = self.env.ref("tenenet_projects.tenenet_organizational_unit_scpp")
        existing = self.env["hr.employee"].create({
            "name": "Testovacia Logopedička",
            "work_email": "test.logoped@tenenet.sk",
            "organizational_unit_id": self.env.ref("tenenet_projects.tenenet_organizational_unit_tenenet_oz").id,
        })

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            self._write_csv(
                tmp_path / "hr_department_import_ready.csv",
                ["id", "name"],
                [{"id": "dept_specialna_pedagogika_terapie", "name": "Špeciálna pedagogika a terapie"}],
            )
            self._write_csv(
                tmp_path / "hr_job_import_ready.csv",
                ["id", "name", "x_department_code"],
                [{"id": "job_logoped", "name": "Logopéd", "x_department_code": "dept_specialna_pedagogika_terapie"}],
            )
            self._write_csv(
                tmp_path / "hr_employee_import_ready.csv",
                self.cleanup_script.EMPLOYEE_HEADERS,
                [{
                    "id": "emp_testovacia_logopedicka",
                    "title_academic": "Mgr.",
                    "name": "Testovacia Logopedička",
                    "job_id/id": "job_logoped",
                    "department_id/id": "dept_specialna_pedagogika_terapie",
                    "parent_id/id": "",
                    "address_id/id": "loc_senec",
                    "work_location": "Senec",
                    "main_site_name": "Senec",
                    "secondary_site_names": "",
                    "organizational_unit_id/id": "tenenet_organizational_unit_scpp",
                    "contract_position": "logopéd",
                    "work_email": "test.logoped@tenenet.sk",
                    "private_phone": "",
                    "work_phone": "+421 910 549 005",
                    "x_source_row": "10",
                    "x_raw_employer": "SCPaP",
                    "x_org_unit_code": "SCPP",
                    "x_org_unit_mapping_status": "mapped",
                    "x_raw_program": "SCPaP",
                    "x_program_normalized": "SCPAP",
                    "x_wage_program_code": "SCPAP",
                    "x_raw_contract_position": "logopéd",
                    "x_raw_position": "logopéd",
                    "x_raw_manager": "",
                    "x_location_unresolved": "",
                    "x_import_action": "import",
                    "x_skip_reason": "",
                    "x_normalization_status": "ready",
                    "x_review_note": "",
                }],
            )

            result = self.import_script.import_ready_directory(self.env, tmp_path)

        updated = self.env["hr.employee"].search([("work_email", "=", "test.logoped@tenenet.sk")])
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated, existing)
        self.assertEqual(updated.organizational_unit_id, org_unit)
        self.assertEqual(updated.contract_position, "logopéd")
        self.assertFalse(updated.private_phone)
        self.assertEqual(updated.work_phone, "+421 910 549 005")
        self.assertEqual(updated.wage_program_override_id.code, "SCPAP")
        self.assertEqual(updated.main_site_id.name, "Senec")
        self.assertEqual(result["employees"], 1)

    def _write_csv(self, path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
