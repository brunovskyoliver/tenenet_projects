from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan12ProjectYearlyLaborReport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee_a = self.env["hr.employee"].create({"name": "Adam Zamestnanec", "work_ratio": 200.0})
        self.employee_b = self.env["hr.employee"].create({"name": "Beata Zamestnanec", "work_ratio": 100.0})

        self.project_a = self.env["tenenet.project"].create({"name": "Projekt A"})
        self.project_b = self.env["tenenet.project"].create({"name": "Projekt B"})

        self.assignment_a = self.env["tenenet.project.assignment"].create(
            {
                "employee_id": self.employee_a.id,
                "project_id": self.project_a.id,
                "wage_hm": 10.0,
                "wage_ccp": 20.0,
            }
        )
        self.assignment_b = self.env["tenenet.project.assignment"].create(
            {
                "employee_id": self.employee_b.id,
                "project_id": self.project_a.id,
                "wage_hm": 12.0,
                "wage_ccp": 30.0,
            }
        )
        self.assignment_other_project = self.env["tenenet.project.assignment"].create(
            {
                "employee_id": self.employee_a.id,
                "project_id": self.project_b.id,
                "wage_hm": 10.0,
                "wage_ccp": 20.0,
            }
        )
        self.report = self.env.ref("tenenet_projects.tenenet_project_yearly_labor_report")

    def _create_timesheet(self, assignment, period, hours_total):
        return self.env["tenenet.project.timesheet"].create(
            {
                "assignment_id": assignment.id,
                "period": period,
                "hours_pp": hours_total,
            }
        )

    def _get_lines(self, project, date_to, unfolded_lines=None):
        options_data = {
            "project_ids": [project.id],
            "date": {
                "mode": "single",
                "filter": "custom",
                "date_to": date_to,
            },
        }
        if unfolded_lines:
            options_data["unfolded_lines"] = unfolded_lines
        options = self.report.get_options(options_data)
        return self.report._get_lines(options), options

    def _find_line(self, lines, line_id):
        return next(line for line in lines if line["id"] == line_id)

    def _find_employee_metric_line(self, lines, employee, metric_label):
        return next(
            line
            for line in lines
            if line["name"] == employee.name and self._column_map(line)["metric_label"] == metric_label
        )

    def _find_total_line(self, lines, line_name):
        return next(line for line in lines if line["name"] == line_name)

    def _find_child_line(self, lines, parent_name, line_name):
        parent_line = self._find_total_line(lines, parent_name)
        return next(
            line
            for line in lines
            if line["name"] == line_name and line.get("parent_id") == parent_line["id"]
        )

    def _column_map(self, line):
        return {
            column["expression_label"]: column["no_format"]
            for column in line["columns"]
        }

    def test_report_returns_two_rows_per_employee_and_total_rows(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", 10.0)
        self._create_timesheet(self.assignment_b, "2026-02-01", 15.0)

        lines, _options = self._get_lines(self.project_a, "2026-12-31")
        self.assertEqual([line["name"] for line in lines], [
            "Adam Zamestnanec",
            "Adam Zamestnanec",
            "Beata Zamestnanec",
            "Beata Zamestnanec",
            "Hodiny spolu",
            "Mzdové náklady spolu",
            "Suma spolu",
        ])

        self.assertEqual(self._column_map(lines[0])["metric_label"], "Celková cena práce")
        self.assertEqual(self._column_map(lines[1])["metric_label"], "Odpracované hodiny")
        self.assertEqual(self._column_map(lines[2])["metric_label"], "Celková cena práce")
        self.assertEqual(self._column_map(lines[3])["metric_label"], "Odpracované hodiny")

    def test_report_adds_project_items_section_between_labor_subtotal_and_final_total(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", 10.0)
        self.env["tenenet.project.expense"].create(
            {
                "project_id": self.project_a.id,
                "allowed_type_id": self.env["tenenet.project.allowed.expense.type"].create({
                    "project_id": self.project_a.id,
                    "name": "Telefón",
                }).id,
                "date": "2026-01-10",
                "amount": 10.18,
                "description": "Telefon januar",
                "charged_to": "project",
            }
        )

        lines, options = self._get_lines(self.project_a, "2026-12-31")
        self.assertEqual([line["name"] for line in lines], [
            "Adam Zamestnanec",
            "Adam Zamestnanec",
            "Hodiny spolu",
            "Mzdové náklady spolu",
            "Projektové výdavky",
            "Suma spolu",
        ])

        project_items_line = self._find_total_line(lines, "Projektové výdavky")
        self.assertTrue(project_items_line["unfoldable"])
        self.assertFalse(project_items_line["unfolded"])
        self.assertEqual(
            project_items_line["expand_function"],
            "_report_expand_unfoldable_line_project_yearly_labor_project_items",
        )

        expanded_lines = self.report.get_expanded_lines(
            options,
            project_items_line["id"],
            project_items_line.get("groupby"),
            project_items_line["expand_function"],
            project_items_line.get("progress"),
            0,
            project_items_line.get("horizontal_split_side"),
        )
        self.assertEqual([line["name"] for line in expanded_lines], ["Telefón"])

    def test_report_month_values_and_year_total_match_timesheets(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", 10.0)
        self._create_timesheet(self.assignment_a, "2026-03-01", 12.5)

        lines, _options = self._get_lines(self.project_a, "2026-12-31")
        amount_line = self._find_employee_metric_line(lines, self.employee_a, "Celková cena práce")
        hours_line = self._find_employee_metric_line(lines, self.employee_a, "Odpracované hodiny")

        amount_columns = self._column_map(amount_line)
        hours_columns = self._column_map(hours_line)

        self.assertEqual(amount_columns["metric_label"], "Celková cena práce")
        self.assertEqual(hours_columns["metric_label"], "Odpracované hodiny")
        self.assertAlmostEqual(amount_columns["month_01"], 136.2, places=2)
        self.assertAlmostEqual(amount_columns["month_03"], 170.25, places=2)
        self.assertAlmostEqual(amount_columns["year_total"], 306.45, places=2)
        self.assertAlmostEqual(hours_columns["month_01"], 10.0, places=2)
        self.assertAlmostEqual(hours_columns["month_03"], 12.5, places=2)
        self.assertAlmostEqual(hours_columns["year_total"], 22.5, places=2)

    def test_report_totals_sum_all_employee_rows(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", 10.0)
        self._create_timesheet(self.assignment_b, "2026-01-01", 15.0)
        self._create_timesheet(self.assignment_b, "2026-02-01", 5.0)

        lines, _options = self._get_lines(self.project_a, "2026-12-31")
        total_hours_line = self._find_total_line(lines, "Hodiny spolu")
        labor_amount_line = self._find_total_line(lines, "Mzdové náklady spolu")
        total_amount_line = lines[-1]

        total_hours_columns = self._column_map(total_hours_line)
        labor_amount_columns = self._column_map(labor_amount_line)
        total_amount_columns = self._column_map(total_amount_line)

        self.assertAlmostEqual(total_hours_columns["month_01"], 25.0, places=2)
        self.assertAlmostEqual(total_hours_columns["month_02"], 5.0, places=2)
        self.assertAlmostEqual(total_hours_columns["year_total"], 30.0, places=2)
        self.assertAlmostEqual(labor_amount_columns["month_01"], 381.36, places=2)
        self.assertAlmostEqual(labor_amount_columns["month_02"], 81.72, places=2)
        self.assertAlmostEqual(labor_amount_columns["year_total"], 463.08, places=2)
        self.assertAlmostEqual(total_amount_columns["month_01"], 381.36, places=2)
        self.assertAlmostEqual(total_amount_columns["month_02"], 81.72, places=2)
        self.assertAlmostEqual(total_amount_columns["year_total"], 463.08, places=2)

    def test_project_items_are_grouped_and_included_in_final_total(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", 10.0)
        allowed_telephone = self.env["tenenet.project.allowed.expense.type"].create({
            "project_id": self.project_a.id,
            "name": "Telefón povolený",
        })
        allowed_rent = self.env["tenenet.project.allowed.expense.type"].create({
            "project_id": self.project_a.id,
            "name": "Nájom fallback",
        })
        cfg_phone = self.env["tenenet.expense.type.config"].create({"name": "Telefón"})

        self.env["tenenet.project.expense"].create(
            {
                "project_id": self.project_a.id,
                "allowed_type_id": allowed_telephone.id,
                "expense_type_config_id": cfg_phone.id,
                "date": "2026-01-10",
                "amount": 10.18,
                "description": "Telefon januar",
                "charged_to": "project",
            }
        )
        self.env["tenenet.project.expense"].create(
            {
                "project_id": self.project_a.id,
                "allowed_type_id": allowed_telephone.id,
                "expense_type_config_id": cfg_phone.id,
                "date": "2026-01-20",
                "amount": 5.00,
                "description": "Telefon dodatok",
                "charged_to": "project",
            }
        )
        self.env["tenenet.project.expense"].create(
            {
                "project_id": self.project_a.id,
                "allowed_type_id": allowed_rent.id,
                "date": "2026-02-01",
                "amount": 120.0,
                "description": "Nájom Lučenec",
                "charged_to": "project",
            }
        )
        self.env["tenenet.project.expense"].create(
            {
                "project_id": self.project_a.id,
                "allowed_type_id": allowed_rent.id,
                "date": "2026-03-01",
                "amount": 999.0,
                "description": "Interný nájom",
                "charged_to": "internal",
            }
        )

        collapsed_lines, _options = self._get_lines(self.project_a, "2026-12-31")
        project_items_line = self._find_total_line(collapsed_lines, "Projektové výdavky")
        lines, _options = self._get_lines(self.project_a, "2026-12-31", unfolded_lines=[project_items_line["id"]])
        labor_total = self._column_map(self._find_total_line(lines, "Mzdové náklady spolu"))
        project_items_total = self._column_map(self._find_total_line(lines, "Projektové výdavky"))
        phone_line = self._column_map(self._find_child_line(lines, "Projektové výdavky", "Telefón"))
        rent_line = self._column_map(self._find_child_line(lines, "Projektové výdavky", "Nájom fallback"))
        final_total = self._column_map(lines[-1])

        self.assertAlmostEqual(labor_total["month_01"], 136.2, places=2)
        self.assertAlmostEqual(project_items_total["month_01"], 15.18, places=2)
        self.assertAlmostEqual(project_items_total["month_02"], 120.0, places=2)
        self.assertAlmostEqual(project_items_total["year_total"], 135.18, places=2)
        self.assertAlmostEqual(phone_line["month_01"], 15.18, places=2)
        self.assertAlmostEqual(phone_line["year_total"], 15.18, places=2)
        self.assertAlmostEqual(rent_line["month_02"], 120.0, places=2)
        self.assertAlmostEqual(rent_line["year_total"], 120.0, places=2)
        self.assertAlmostEqual(final_total["month_01"], 151.38, places=2)
        self.assertAlmostEqual(final_total["month_02"], 120.0, places=2)
        self.assertAlmostEqual(final_total["year_total"], 271.38, places=2)

    def test_project_items_fallback_to_allowed_type_name_when_catalog_link_is_missing(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", 10.0)
        allowed_misc = self.env["tenenet.project.allowed.expense.type"].create({
            "project_id": self.project_a.id,
            "name": "Internet",
        })
        self.env["tenenet.project.expense"].create(
            {
                "project_id": self.project_a.id,
                "allowed_type_id": allowed_misc.id,
                "date": "2026-04-01",
                "amount": 50.0,
                "description": "Internet mesačne",
                "charged_to": "project",
            }
        )

        collapsed_lines, _options = self._get_lines(self.project_a, "2026-12-31")
        project_items_line = self._find_total_line(collapsed_lines, "Projektové výdavky")
        lines, _options = self._get_lines(self.project_a, "2026-12-31", unfolded_lines=[project_items_line["id"]])
        expense_line = self._column_map(self._find_child_line(lines, "Projektové výdavky", "Internet"))
        self.assertAlmostEqual(expense_line["month_04"], 50.0, places=2)

    def test_project_and_year_filters_change_dataset(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", 10.0)
        self._create_timesheet(self.assignment_a, "2027-01-01", 20.0)
        self._create_timesheet(self.assignment_other_project, "2026-01-01", 30.0)

        project_a_2026, _options = self._get_lines(self.project_a, "2026-12-31")
        project_a_2027, _options = self._get_lines(self.project_a, "2027-12-31")
        project_b_2026, _options = self._get_lines(self.project_b, "2026-12-31")

        project_a_2026_hours = self._column_map(
            self._find_employee_metric_line(project_a_2026, self.employee_a, "Odpracované hodiny")
        )
        project_a_2027_hours = self._column_map(
            self._find_employee_metric_line(project_a_2027, self.employee_a, "Odpracované hodiny")
        )
        project_b_2026_hours = self._column_map(
            self._find_employee_metric_line(project_b_2026, self.employee_a, "Odpracované hodiny")
        )

        self.assertAlmostEqual(project_a_2026_hours["year_total"], 10.0, places=2)
        self.assertAlmostEqual(project_a_2027_hours["year_total"], 20.0, places=2)
        self.assertAlmostEqual(project_b_2026_hours["year_total"], 30.0, places=2)

    def test_only_employees_with_data_are_listed(self):
        self._create_timesheet(self.assignment_a, "2026-01-01", 10.0)

        lines, _options = self._get_lines(self.project_a, "2026-12-31")
        employee_rows = [
            (line["name"], column_map["metric_label"])
            for line in lines
            for column_map in [self._column_map(line)]
            if line["name"] not in {"Hodiny spolu", "Mzdové náklady spolu", "Projektové výdavky", "Suma spolu"}
            and column_map.get("metric_label") in {"Celková cena práce", "Odpracované hodiny"}
        ]

        self.assertIn(("Adam Zamestnanec", "Odpracované hodiny"), employee_rows)
        self.assertNotIn(("Beata Zamestnanec", "Odpracované hodiny"), employee_rows)

    def test_project_items_are_hidden_while_collapsed_and_visible_after_unfold(self):
        allowed_telephone = self.env["tenenet.project.allowed.expense.type"].create({
            "project_id": self.project_a.id,
            "name": "Telefón",
        })
        self.env["tenenet.project.expense"].create(
            {
                "project_id": self.project_a.id,
                "allowed_type_id": allowed_telephone.id,
                "date": "2026-05-01",
                "amount": 22.5,
                "description": "Telefon maj",
                "charged_to": "project",
            }
        )

        collapsed_lines, _options = self._get_lines(self.project_a, "2026-12-31")
        self.assertEqual([line["name"] for line in collapsed_lines], [
            "Hodiny spolu",
            "Mzdové náklady spolu",
            "Projektové výdavky",
            "Suma spolu",
        ])

        project_items_line = self._find_total_line(collapsed_lines, "Projektové výdavky")
        unfolded_lines, _options = self._get_lines(
            self.project_a,
            "2026-12-31",
            unfolded_lines=[project_items_line["id"]],
        )
        self.assertEqual([line["name"] for line in unfolded_lines], [
            "Hodiny spolu",
            "Mzdové náklady spolu",
            "Projektové výdavky",
            "Telefón",
            "Suma spolu",
        ])
