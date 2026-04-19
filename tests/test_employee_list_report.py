from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetEmployeeListReport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.report = self.env.ref("tenenet_projects.tenenet_employee_list_report")
        self.language_skill_type = self.env.ref("hr_skills.hr_skill_type_lang")
        self.language_skill_level = self.language_skill_type.skill_level_ids[:1]
        self.english = self.env["hr.skill"].search([
            ("skill_type_id", "=", self.language_skill_type.id),
            ("name", "=", "English"),
        ], limit=1)
        self.german = self.env["hr.skill"].search([
            ("skill_type_id", "=", self.language_skill_type.id),
            ("name", "=", "German"),
        ], limit=1)
        if not self.english:
            self.english = self.language_skill_type.skill_ids[:1]
        if not self.german:
            self.german = (self.language_skill_type.skill_ids - self.english)[:1]
        self.job_psychologist = self.env["hr.job"].create({"name": "Psychológ"})
        self.job_coordinator = self.env["hr.job"].create({"name": "Koordinátor"})
        self.site_bratislava = self.env["tenenet.project.site"].create({
            "name": "Bratislava centrum",
            "site_type": "centrum",
        })
        self.site_trnava = self.env["tenenet.project.site"].create({
            "name": "Trnava prevádzka",
            "site_type": "prevadzka",
        })
        self.site_nitra = self.env["tenenet.project.site"].create({
            "name": "Nitra centrum",
            "site_type": "centrum",
        })
        self.program = self.env["tenenet.program"].create({"name": "Report Program", "code": "RPT"})
        self.international_project = self.env["tenenet.project"].create({
            "name": "Medzinárodný projekt",
            "project_type": "medzinarodny",
        })
        self.project = self.env["tenenet.project"].create({
            "name": "Report Project",
            "program_ids": [(4, self.program.id)],
        })
        self.manager = self.env["hr.employee"].create({
            "name": "Mgr. Jana Vedúca",
            "work_phone": "+421901000100",
        })
        self.employee_partial = self.env["hr.employee"].create({
            "tenenet_number": 17,
            "title_academic": "Mgr.",
            "last_name": "Zamestnanec",
            "first_name": "Adam",
            "job_id": self.job_psychologist.id,
            "position": "Psychológ",
            "study_field": "Psychológia",
            "parent_id": self.manager.id,
            "work_ratio": 100.0,
            "work_phone": "+421901111222",
            "main_site_id": self.site_bratislava.id,
            "secondary_site_ids": [(6, 0, self.site_trnava.ids)],
            "additional_job_ids": [(6, 0, self.job_coordinator.ids)],
            "experience_years_total": 6.0,
        })
        self.employee_full = self.env["hr.employee"].create({
            "tenenet_number": 18,
            "title_academic": "Bc.",
            "last_name": "Kolegyňa",
            "first_name": "Beata",
            "job_id": self.job_coordinator.id,
            "position": "Koordinátorka",
            "study_field": "Manažment",
            "parent_id": self.manager.id,
            "work_ratio": 100.0,
            "work_phone": "+421902333444",
            "main_site_id": self.site_nitra.id,
        })
        self.employee_free = self.env["hr.employee"].create({
            "tenenet_number": 19,
            "last_name": "Voľný",
            "first_name": "Cyril",
            "job_id": self.job_psychologist.id,
            "position": "Psychológ",
            "study_field": "Sociálna práca",
            "work_ratio": 100.0,
            "main_site_id": self.site_trnava.id,
        })
        self.employee_without_job = self.env["hr.employee"].create({
            "tenenet_number": 20,
            "last_name": "Bezová",
            "first_name": "Dana",
            "study_field": "Andragogika",
            "work_ratio": 50.0,
        })
        self.env["hr.employee.skill"].create({
            "employee_id": self.employee_partial.id,
            "skill_type_id": self.language_skill_type.id,
            "skill_id": self.english.id,
            "skill_level_id": self.language_skill_level.id,
        })
        self.env["hr.employee.skill"].create({
            "employee_id": self.employee_full.id,
            "skill_type_id": self.language_skill_type.id,
            "skill_id": self.german.id,
            "skill_level_id": self.language_skill_level.id,
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_partial.id,
            "project_id": self.project.id,
            "program_id": self.program.id,
            "allocation_ratio": 40.0,
            "wage_hm": 10.0,
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_full.id,
            "project_id": self.project.id,
            "program_id": self.program.id,
            "allocation_ratio": 100.0,
            "wage_hm": 10.0,
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_partial.id,
            "project_id": self.international_project.id,
            "allocation_ratio": 10.0,
            "wage_hm": 10.0,
        })
        (self.employee_partial | self.employee_full | self.employee_free | self.employee_without_job).invalidate_recordset()

    def _create_timesheet(self, assignment, period, **hours):
        timesheet = self.env["tenenet.project.timesheet"]._get_or_create_for_assignment_period(assignment, period)
        if hours:
            timesheet.with_context(from_hr_leave_sync=True).write(hours)
        return timesheet

    def _get_lines(self, **options_data):
        options = self.report.get_options(options_data)
        return self.report._get_lines(options)

    def _column_map(self, line):
        return {
            column["expression_label"]: column["no_format"]
            for column in line["columns"]
        }

    def _employee_lines(self, **options_data):
        return [
            line for line in self._get_lines(**options_data)
            if self._column_map(line).get("employee_name")
        ]

    def _employee_line(self, employee_name, **options_data):
        return next(
            line for line in self._employee_lines(**options_data)
            if self._column_map(line)["employee_name"] == employee_name
        )

    def test_report_shows_employee_columns_from_hr_fields(self):
        line = self._employee_line(self.employee_partial.name)
        columns = self._column_map(line)

        self.assertEqual(columns["employee_name"], "Mgr. Adam Zamestnanec")
        self.assertEqual(columns["tenenet_number"], "17")
        self.assertEqual(columns["title_academic"], "Mgr.")
        self.assertEqual(columns["last_name"], "Zamestnanec")
        self.assertEqual(columns["first_name"], "Adam")
        self.assertEqual(columns["position"], "Psychológ")
        self.assertIn("Koordinátor", columns["all_job_names"])
        self.assertEqual(columns["work_phone"], "+421901111222")
        self.assertEqual(columns["study_field"], "Psychológia")
        self.assertEqual(columns["manager_name"], "Mgr. Jana Vedúca")
        self.assertEqual(columns["main_site_name"], "Bratislava centrum")
        self.assertEqual(columns["secondary_site_names"], "Trnava prevádzka")
        self.assertEqual(columns["project_names"], "Medzinárodný projekt, Report Project")
        self.assertEqual(columns["program_names"], "Report Program")
        self.assertAlmostEqual(columns["free_hours"], 4.0, places=2)
        self.assertAlmostEqual(columns["utilization_percentage"], 0.0, places=2)
        self.assertAlmostEqual(columns["work_hours"], 8.0, places=2)

    def test_report_options_include_availability_mode_and_minimum_free_hours(self):
        options = self.report.get_options({})

        self.assertIn("availability_mode", options)
        self.assertFalse(options["availability_mode"])
        self.assertIn("minimum_free_hours", options)
        self.assertEqual(options["minimum_free_hours"], 0.0)

    def test_utilization_column_matches_selected_month(self):
        assignment = self.employee_partial.assignment_ids[:1]
        self._create_timesheet(assignment, "2026-03-01", hours_pp=120.0)

        line = self._employee_line(self.employee_partial.name, date={"mode": "single", "filter": "custom", "date_to": "2026-03-18"})
        columns = self._column_map(line)

        utilization = self.env["tenenet.utilization"].search(
            [("employee_id", "=", self.employee_partial.id), ("period", "=", "2026-03-01")],
            limit=1,
        )
        self.assertTrue(utilization)
        self.assertAlmostEqual(columns["utilization_percentage"], utilization.utilization_percentage, places=2)

    def test_utilization_column_changes_when_month_changes(self):
        assignment = self.employee_partial.assignment_ids[:1]
        self._create_timesheet(assignment, "2026-01-01", hours_pp=40.0)
        self._create_timesheet(assignment, "2026-02-01", hours_pp=80.0)

        january_columns = self._column_map(
            self._employee_line(
                self.employee_partial.name,
                date={"mode": "single", "filter": "custom", "date_to": "2026-01-10"},
            )
        )
        february_columns = self._column_map(
            self._employee_line(
                self.employee_partial.name,
                date={"mode": "single", "filter": "custom", "date_to": "2026-02-10"},
            )
        )

        self.assertNotEqual(january_columns["utilization_percentage"], february_columns["utilization_percentage"])

    def test_grouped_modes_keep_utilization_column(self):
        assignment = self.employee_partial.assignment_ids[:1]
        self._create_timesheet(assignment, "2026-04-01", hours_pp=96.0)

        line = self._employee_line(
            self.employee_partial.name,
            grouping_mode="availability",
            date={"mode": "single", "filter": "custom", "date_to": "2026-04-05"},
        )
        columns = self._column_map(line)

        self.assertGreater(columns["utilization_percentage"], 0.0)

    def test_utilization_column_defaults_to_zero_without_month_data(self):
        line = self._employee_line(
            self.employee_partial.name,
            date={"mode": "single", "filter": "custom", "date_to": "2030-01-10"},
        )
        columns = self._column_map(line)

        self.assertAlmostEqual(columns["utilization_percentage"], 0.0, places=2)

    def test_report_search_filters_employee_rows(self):
        line_names = [self._column_map(line)["employee_name"] for line in self._employee_lines(filter_search_bar="adam")]

        self.assertIn(self.employee_partial.name, line_names)
        self.assertNotIn(self.employee_full.name, line_names)

    def test_profession_filter_returns_only_matching_employees(self):
        line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(job_ids=[self.job_psychologist.id])
        ]

        self.assertIn(self.employee_partial.name, line_names)
        self.assertIn(self.employee_free.name, line_names)
        self.assertNotIn(self.employee_full.name, line_names)
        self.assertNotIn(self.employee_without_job.name, line_names)

    def test_profession_filter_matches_additional_jobs(self):
        line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(job_ids=[self.job_coordinator.id])
        ]

        self.assertIn(self.employee_partial.name, line_names)
        self.assertIn(self.employee_full.name, line_names)
        self.assertNotIn(self.employee_free.name, line_names)

    def test_main_site_filter_returns_only_matching_employees(self):
        line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(main_site_ids=[self.site_trnava.id])
        ]

        self.assertEqual(line_names, [self.employee_free.name])

    def test_language_filter_returns_only_matching_employees(self):
        line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(language_skill_ids=[self.english.id])
        ]

        self.assertIn(self.employee_partial.name, line_names)
        self.assertNotIn(self.employee_full.name, line_names)

    def test_availability_filter_returns_only_matching_employees(self):
        line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(
                availability_mode="full"
            )
        ]

        self.assertEqual(line_names, [self.employee_full.name])

    def test_free_availability_filter_with_zero_threshold_returns_positive_free_capacity(self):
        line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(
                availability_mode="free",
                minimum_free_hours=0,
            )
        ]

        self.assertIn(self.employee_partial.name, line_names)
        self.assertIn(self.employee_free.name, line_names)
        self.assertIn(self.employee_without_job.name, line_names)
        self.assertNotIn(self.employee_full.name, line_names)

    def test_free_availability_filter_with_threshold_returns_only_matching_employees(self):
        line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(
                availability_mode="free",
                minimum_free_hours=4,
            )
        ]

        self.assertIn(self.employee_partial.name, line_names)
        self.assertIn(self.employee_free.name, line_names)
        self.assertNotIn(self.employee_without_job.name, line_names)
        self.assertNotIn(self.employee_full.name, line_names)

    def test_search_and_filters_work_together(self):
        line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(
                filter_search_bar="bea",
                availability_mode="full",
                job_ids=[self.job_coordinator.id],
            )
        ]

        self.assertEqual(line_names, [self.employee_full.name])

    def test_project_and_program_filters_limit_employee_rows(self):
        line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(
                project_ids=[self.project.id],
                program_ids=[self.program.id],
            )
        ]

        self.assertIn(self.employee_partial.name, line_names)
        self.assertIn(self.employee_full.name, line_names)
        self.assertNotIn(self.employee_free.name, line_names)

    def test_grouping_by_profession_creates_sections(self):
        lines = self._get_lines(grouping_mode="profession")
        section_names = [line["name"] for line in lines if line["name"]]
        bez_profesie_index = next(index for index, line in enumerate(lines) if line["name"] == "Bez profesie")
        psycholog_index = next(index for index, line in enumerate(lines) if line["name"] == "Psychológ")
        dana_index = next(
            index for index, line in enumerate(lines)
            if self._column_map(line).get("employee_name") == self.employee_without_job.name
        )
        adam_index = next(
            index for index, line in enumerate(lines)
            if self._column_map(line).get("employee_name") == self.employee_partial.name
        )

        self.assertIn("Psychológ", section_names)
        self.assertIn("Koordinátor", section_names)
        self.assertIn("Bez profesie", section_names)
        self.assertLess(bez_profesie_index, dana_index)
        self.assertLess(psycholog_index, adam_index)

    def test_grouping_by_availability_creates_sections(self):
        lines = self._get_lines(grouping_mode="availability")
        section_names = [line["name"] for line in lines if line["name"]]
        free_index = next(index for index, line in enumerate(lines) if line["name"] == "Voľný")
        partial_index = next(index for index, line in enumerate(lines) if line["name"] == "Čiastočne alokovaný")
        full_index = next(index for index, line in enumerate(lines) if line["name"] == "Plne alokovaný")
        cyril_index = next(
            index for index, line in enumerate(lines)
            if self._column_map(line).get("employee_name") == self.employee_free.name
        )
        adam_index = next(
            index for index, line in enumerate(lines)
            if self._column_map(line).get("employee_name") == self.employee_partial.name
        )
        beata_index = next(
            index for index, line in enumerate(lines)
            if self._column_map(line).get("employee_name") == self.employee_full.name
        )

        self.assertEqual(section_names[:3], ["Voľný", "Čiastočne alokovaný", "Plne alokovaný"])
        self.assertLess(free_index, cyril_index)
        self.assertLess(partial_index, adam_index)
        self.assertLess(full_index, beata_index)

    def test_employees_without_phone_or_languages_do_not_break_report(self):
        line = self._employee_line(self.employee_without_job.name)
        columns = self._column_map(line)

        self.assertEqual(columns["work_phone"], "")
        self.assertEqual(columns["study_field"], "Andragogika")

    def test_search_matches_secondary_workplace_and_all_positions(self):
        site_line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(filter_search_bar="trnava")
        ]
        job_line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(filter_search_bar="koordinátor")
        ]

        self.assertIn(self.employee_partial.name, site_line_names)
        self.assertIn(self.employee_free.name, site_line_names)
        self.assertIn(self.employee_partial.name, job_line_names)
        self.assertIn(self.employee_full.name, job_line_names)

    def test_employees_without_job_are_handled_in_grouped_mode(self):
        lines = self._get_lines(grouping_mode="profession")
        bez_profesie_index = next(index for index, line in enumerate(lines) if line["name"] == "Bez profesie")
        dana_index = next(
            index for index, line in enumerate(lines)
            if self._column_map(line).get("employee_name") == self.employee_without_job.name
        )

        self.assertLess(bez_profesie_index, dana_index)
