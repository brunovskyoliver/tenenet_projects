from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetProjectSummaryReport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.report = self.env.ref("tenenet_projects.tenenet_project_summary_report")
        self.program = self.env["tenenet.program"].create({
            "name": "Program Summary",
            "code": "PG_SUMMARY",
        })
        self.other_program = self.env["tenenet.program"].create({
            "name": "Program Hidden Summary",
            "code": "PG_SUMMARY_HIDDEN",
        })
        self.donor = self.env["tenenet.donor"].create({"name": "Donor Summary"})
        self.other_donor = self.env["tenenet.donor"].create({"name": "Donor Hidden Summary"})
        self.pm_user = self._create_user("summary_pm_user", [self.env.ref("base.group_user").id])
        self.pm_employee = self.env["hr.employee"].create({
            "name": "Summary PM",
            "user_id": self.pm_user.id,
        })
        self.visible_project = self.env["tenenet.project"].create({
            "name": "Visible Summary Project",
            "description": "Dlhá poznámka projektu pre sumár.",
            "project_type": "narodny",
            "program_ids": [Command.link(self.program.id)],
            "donor_id": self.donor.id,
            "project_manager_id": self.pm_employee.id,
            "contract_number": "SUM-2026",
            "date_start": "2026-01-01",
            "date_end": "2026-12-31",
            "date_contract": "2026-01-10",
            "semaphore": "green",
            "portal": "https://portal.example.test",
        })
        self.other_project = self.env["tenenet.project"].create({
            "name": "Hidden Summary Project",
            "project_type": "sluzby",
            "program_ids": [Command.link(self.other_program.id)],
            "donor_id": self.other_donor.id,
            "date_start": "2026-01-01",
            "date_end": "2026-12-31",
        })
        self.no_date_project = self.env["tenenet.project"].create({
            "name": "No Date Summary Project",
            "project_type": "narodny",
            "program_ids": [Command.link(self.program.id)],
        })
        self.internal_project = self.env["tenenet.project"].with_context(active_test=False).search(
            [("is_tenenet_internal", "=", True)],
            limit=1,
        )
        self.env["tenenet.project.budget.line"].create({
            "name": "Summary Budget 2026",
            "project_id": self.visible_project.id,
            "program_id": self.program.id,
            "year": 2026,
            "budget_type": "labor",
            "amount": 1000.0,
        })
        self.env["tenenet.project.budget.line"].create({
            "name": "Summary Budget 2025",
            "project_id": self.visible_project.id,
            "program_id": self.program.id,
            "year": 2025,
            "budget_type": "labor",
            "amount": 500.0,
        })
        self.env["tenenet.project.receipt"].create({
            "project_id": self.visible_project.id,
            "date_received": "2026-02-01",
            "amount": 700.0,
        })
        self.env["tenenet.project.receipt"].create({
            "project_id": self.visible_project.id,
            "date_received": "2025-02-01",
            "amount": 200.0,
        })
        self.pm_user.invalidate_recordset(["group_ids"])

    def _create_user(self, login, group_ids):
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": login,
            "login": login,
            "email": f"{login}@example.com",
            "company_id": self.env.company.id,
            "company_ids": [Command.set([self.env.company.id])],
            "group_ids": [Command.set(group_ids)],
        })

    def _get_lines(self, **options_data):
        options = self.report.get_options(options_data)
        return self.report._get_lines(options)

    def _column_map(self, line):
        return {
            column["expression_label"]: column["no_format"]
            for column in line["columns"]
        }

    def _project_lines(self, **options_data):
        return [
            line for line in self._get_lines(**options_data)
            if self._column_map(line).get("project_name")
        ]

    def _project_line(self, project_name, **options_data):
        return next(
            line for line in self._project_lines(**options_data)
            if self._column_map(line)["project_name"] == project_name
        )

    def test_report_options_include_custom_filters(self):
        options = self.report.get_options({})

        self.assertEqual(options["project_scope"], "active_year")
        self.assertIn("project_type_selection", options)
        self.assertIn("semaphore_selection", options)
        self.assertIn("available_program_domain", options)
        self.assertIn("available_donor_domain", options)

    def test_report_columns_start_with_year_project_program(self):
        columns = self.report.column_ids.sorted("sequence")

        self.assertEqual(columns[:3].mapped("expression_label"), ["year_label", "project_name", "program"])
        self.assertEqual(columns[:3].mapped("name"), ["Rok", "Projekt", "Program"])
        self.assertNotIn("project_code", columns.mapped("expression_label"))

    def test_report_line_maps_project_summary_columns(self):
        line = self._project_line(
            self.visible_project.name,
            date={"mode": "single", "filter": "custom", "date_to": "2026-06-01"},
        )
        columns = self._column_map(line)

        self.assertEqual(columns["year_label"], "2026")
        self.assertEqual(columns["semaphore_label"], "Zelená")
        self.assertEqual(columns["project_name"], self.visible_project.name)
        self.assertEqual(columns["contract_number"], "SUM-2026")
        self.assertEqual(columns["project_type_label"], "Národný")
        self.assertEqual(columns["donor"], self.donor.display_name)
        self.assertEqual(columns["program"], self.program.display_name)
        self.assertEqual(columns["project_staff"], self.pm_employee.name)
        self.assertEqual(columns["portal"], "https://portal.example.test")
        self.assertAlmostEqual(columns["project_budget"], 1000.0, places=2)
        self.assertAlmostEqual(columns["received_selected_year"], 700.0, places=2)
        self.assertAlmostEqual(columns["received_total"], 900.0, places=2)
        self.assertAlmostEqual(columns["received_diff"], -100.0, places=2)

    def test_active_year_scope_excludes_projects_without_dates_and_internal_projects(self):
        names = [
            self._column_map(line)["project_name"]
            for line in self._project_lines(date={"mode": "single", "filter": "custom", "date_to": "2026-06-01"})
        ]

        self.assertIn(self.visible_project.name, names)
        self.assertIn(self.other_project.name, names)
        self.assertNotIn(self.no_date_project.name, names)
        self.assertNotIn(self.internal_project.name, names)

    def test_all_scope_includes_accessible_projects_without_dates(self):
        names = [
            self._column_map(line)["project_name"]
            for line in self._project_lines(
                project_scope="all",
                date={"mode": "single", "filter": "custom", "date_to": "2026-06-01"},
            )
        ]

        self.assertIn(self.no_date_project.name, names)

    def test_program_donor_type_and_semaphore_filters(self):
        filtered_names = [
            self._column_map(line)["project_name"]
            for line in self._project_lines(
                program_ids=[self.program.id],
                donor_ids=[self.donor.id],
                project_type="narodny",
                semaphore="green",
                date={"mode": "single", "filter": "custom", "date_to": "2026-06-01"},
            )
        ]

        self.assertIn(self.visible_project.name, filtered_names)
        self.assertNotIn(self.other_project.name, filtered_names)

    def test_pm_handler_access_is_limited_to_own_projects(self):
        handler = self.env["tenenet.project.summary.report.handler"].with_user(self.pm_user)
        projects = handler._get_filtered_projects({
            "date": {"date_to": "2026-06-01"},
            "project_scope": "active_year",
        })

        self.assertIn(self.visible_project, projects)
        self.assertNotIn(self.other_project, projects)
