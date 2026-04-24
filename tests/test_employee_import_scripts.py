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
        cls.payroll_import_script = _load_module(
            "tenenet_import_employee_payroll_from_xlsx",
            scripts_dir / "import_employee_payroll_from_xlsx.py",
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

    def test_payroll_xlsx_updates_existing_employee_profile_and_salary(self):
        org_unit = self.env.ref("tenenet_projects.tenenet_organizational_unit_wellnea")
        existing = self.env["hr.employee"].create({
            "name": "Zpsová Testa",
            "work_email": "payroll.zps.test@example.invalid",
            "organizational_unit_id": self.env.ref("tenenet_projects.tenenet_organizational_unit_tenenet_oz").id,
        })

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            self._write_ready_import_fixture(
                tmp_path,
                [{
                    "id": "emp_zpsova_testa",
                    "name": "Zpsová Testa",
                    "work_email": "payroll.zps.test@example.invalid",
                    "x_org_unit_code": "TENENET_OZ",
                    "organizational_unit_id/id": "tenenet_organizational_unit_tenenet_oz",
                    "job_id/id": "job_manikerka",
                    "department_id/id": "dept_prevadzka_podpora",
                    "contract_position": "manikérka",
                    "x_wage_program_code": "",
                }],
            )
            xlsx_path = tmp_path / "payroll.xlsx"
            self._write_payroll_xlsx(xlsx_path, [{
                "Zamestnávateľ": "Wellnea",
                "Titul": "",
                "Priezvisko a meno": "Zpsová Testa",
                "Program,do ktorého patria": "IDA",
                "Dátum nar.": "1987-12-08",
                "Pozícia podľa pracovnej zmluvy": "manikérka",
                "Počet rokov praxe k 01.01.2025": 12,
                "Pozícia": "manikérka",
                "Priamy nadriadený": "",
                "Vzdelanie": "Stredná odborná škola",
                "Odbor": "kozmetika",
                "Lokácia": "Senec",
                "Email": "payroll.zps.test@example.invalid",
                "Dátum nástupu do zamestnania": "2010-08-01",
                "Dátum ukončenia PP": None,
                "Pracovný pomer": "HPP",
                "Miesto výkonu": "Senec",
                "ZPS/ŤZP": "ŤZP",
                "Druh mzdy": "mesačná mzda",
                "Úväzok (hod)": 8,
                "Odvody": 1.307,
                "Hodinová mzda": 7.3422619048,
                "Mzda 12/2025": 1215,
                "Mzda 01/2026": 1233.5,
            }])

            result = self.payroll_import_script.import_payroll_xlsx(self.env, xlsx_path, tmp_path)

        existing.invalidate_recordset()
        self.assertEqual(result["source_rows"], 1)
        self.assertEqual(existing.organizational_unit_id, org_unit)
        self.assertEqual(existing.birthday.isoformat(), "1987-12-08")
        self.assertEqual(existing.contract_date_start.isoformat(), "2010-08-01")
        self.assertAlmostEqual(existing.experience_years_total, 12.0, places=2)
        self.assertAlmostEqual(existing.work_ratio, 100.0, places=2)
        if "disabled" in existing._fields:
            self.assertTrue(existing.disabled)
        self.assertEqual(existing.tenenet_disability_type, "zps")
        self.assertAlmostEqual(existing.tenenet_payroll_contribution_multiplier, 1.307, places=4)
        self.assertAlmostEqual(existing.monthly_gross_salary_target, 1233.5 * 1.307, places=2)
        self.assertAlmostEqual(existing.monthly_gross_salary_target_hm, 1233.5, places=2)
        self.assertIn("Stredná odborná škola", existing.education_info)
        self.assertIn("kozmetika", existing.education_info)

    def test_payroll_xlsx_merges_duplicate_rows_and_uses_latest_salary(self):
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            self._write_ready_import_fixture(tmp_path, [])
            xlsx_path = tmp_path / "payroll.xlsx"
            base_row = {
                "Zamestnávateľ": "Tenenet",
                "Titul": "Mgr.",
                "Priezvisko a meno": "Testová Jana",
                "Program,do ktorého patria": "SPODaSK",
                "Dátum nar.": "1990-01-01",
                "Pozícia podľa pracovnej zmluvy": "sociálny pracovník",
                "Počet rokov praxe k 01.01.2025": 5,
                "Pozícia": "sociálny pracovník",
                "Priamy nadriadený": "",
                "Vzdelanie": "Univerzita",
                "Odbor": "sociálna práca",
                "Lokácia": "Senec",
                "Email": "jana.testova@example.test",
                "Dátum nástupu do zamestnania": "2020-01-01",
                "Dátum ukončenia PP": None,
                "Pracovný pomer": "HPP",
                "Miesto výkonu": "Senec",
                "ZPS/ŤZP": "",
                "Druh mzdy": "mesačná mzda",
                "Úväzok (hod)": 6,
                "Odvody": 1.362,
                "Hodinová mzda": 0,
                "Mzda 12/2025": 1000,
                "Mzda 01/2026": 1100,
            }
            second_row = dict(base_row, **{
                "Program,do ktorého patria": "APZ",
                "Úväzok (hod)": 2,
                "Mzda 12/2025": 200,
                "Mzda 01/2026": 250,
            })
            self._write_payroll_xlsx(xlsx_path, [base_row, second_row])

            result = self.payroll_import_script.import_payroll_xlsx(self.env, xlsx_path, tmp_path)

        employee = self.env["hr.employee"].search([("work_email", "=", "jana.testova@example.test")])
        self.assertEqual(len(employee), 1)
        self.assertEqual(len(result["created"]), 1)
        self.assertEqual(len(result["duplicate_merges"]), 1)
        self.assertAlmostEqual(employee.work_ratio, 100.0, places=2)
        self.assertAlmostEqual(employee.monthly_gross_salary_target, (1100 + 250) * 1.362, places=2)
        self.assertEqual(len(result["salary_changes"]), 2)

    def _write_csv(self, path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

    def _write_ready_import_fixture(self, tmp_path: Path, employees: list[dict[str, str]]) -> None:
        self._write_csv(
            tmp_path / "hr_department_import_ready.csv",
            ["id", "name"],
            [{"id": "dept_prevadzka_podpora", "name": "Prevádzka a podpora"}],
        )
        self._write_csv(
            tmp_path / "hr_job_import_ready.csv",
            ["id", "name", "x_department_code"],
            [{"id": "job_manikerka", "name": "manikérka", "x_department_code": "dept_prevadzka_podpora"}],
        )
        rows = []
        for employee in employees:
            row = {header: "" for header in self.cleanup_script.EMPLOYEE_HEADERS}
            row.update({
                "id": employee["id"],
                "name": employee["name"],
                "job_id/id": employee.get("job_id/id", "job_manikerka"),
                "department_id/id": employee.get("department_id/id", "dept_prevadzka_podpora"),
                "organizational_unit_id/id": employee.get("organizational_unit_id/id", "tenenet_organizational_unit_tenenet_oz"),
                "work_email": employee.get("work_email", ""),
                "contract_position": employee.get("contract_position", ""),
                "x_org_unit_code": employee.get("x_org_unit_code", "TENENET_OZ"),
                "x_wage_program_code": employee.get("x_wage_program_code", ""),
                "x_import_action": "import",
            })
            rows.append(row)
        self._write_csv(tmp_path / "hr_employee_import_ready.csv", self.cleanup_script.EMPLOYEE_HEADERS, rows)

    def _write_payroll_xlsx(self, path: Path, rows: list[dict[str, object]]) -> None:
        from openpyxl import Workbook

        headers = [
            "Zamestnávateľ",
            "Osobné číslo",
            "Titul",
            "Priezvisko a meno",
            "Program,do ktorého patria",
            "Dátum nar.",
            "Pozícia podľa pracovnej zmluvy",
            "Počet rokov praxe k 01.01.2025",
            "Pozícia",
            "Priamy nadriadený",
            "Vzdelanie",
            "Odbor",
            "Lokácia",
            "Email",
            "Dátum nástupu do zamestnania",
            "Dátum ukončenia PP",
            "Pracovný pomer",
            "Miesto výkonu",
            "ZPS/ŤZP",
            "Druh mzdy",
            "Úväzok (hod)",
            "Odvody",
            "Hodinová mzda",
            "Mzda 12/2025",
            "Mzda 01/2026",
        ]
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "all"
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(header) for header in headers])
        workbook.save(path)
