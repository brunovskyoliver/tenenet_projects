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
        self.project = self.env["tenenet.project"].create({"name": "Report Project"})
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
        })
        self.employee_free = self.env["hr.employee"].create({
            "tenenet_number": 19,
            "last_name": "Voľný",
            "first_name": "Cyril",
            "job_id": self.job_psychologist.id,
            "position": "Psychológ",
            "study_field": "Sociálna práca",
            "work_ratio": 100.0,
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
            "allocation_ratio": 40.0,
            "wage_hm": 10.0,
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_full.id,
            "project_id": self.project.id,
            "allocation_ratio": 100.0,
            "wage_hm": 10.0,
        })
        (self.employee_partial | self.employee_full | self.employee_free | self.employee_without_job).invalidate_recordset()

    def _availability_selection(self, *selected_states):
        available_states = [
            ("free", "Voľný"),
            ("partial", "Čiastočne alokovaný"),
            ("full", "Plne alokovaný"),
            ("overbooked", "Preťažený"),
        ]
        return [
            {"id": state, "name": label, "selected": state in selected_states}
            for state, label in available_states
        ]

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
        self.assertEqual(columns["work_phone"], "+421901111222")
        self.assertEqual(columns["study_field"], "Psychológia")
        self.assertEqual(columns["manager_name"], "Mgr. Jana Vedúca")
        self.assertAlmostEqual(columns["work_hours"], 8.0, places=2)

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

    def test_language_filter_returns_only_matching_employees(self):
        line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(language_skill_ids=[self.english.id])
        ]

        self.assertEqual(line_names, [self.employee_partial.name])

    def test_availability_filter_returns_only_matching_employees(self):
        line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(
                availability_filter_selection=self._availability_selection("full")
            )
        ]

        self.assertEqual(line_names, [self.employee_full.name])

    def test_search_and_filters_work_together(self):
        line_names = [
            self._column_map(line)["employee_name"]
            for line in self._employee_lines(
                filter_search_bar="bea",
                availability_filter_selection=self._availability_selection("full"),
                job_ids=[self.job_coordinator.id],
            )
        ]

        self.assertEqual(line_names, [self.employee_full.name])

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

    def test_employees_without_job_are_handled_in_grouped_mode(self):
        lines = self._get_lines(grouping_mode="profession")
        bez_profesie_index = next(index for index, line in enumerate(lines) if line["name"] == "Bez profesie")
        dana_index = next(
            index for index, line in enumerate(lines)
            if self._column_map(line).get("employee_name") == self.employee_without_job.name
        )

        self.assertLess(bez_profesie_index, dana_index)
