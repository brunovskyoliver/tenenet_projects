from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan02Project(TransactionCase):
    def setUp(self):
        super().setUp()
        self.donor_partner = self.env["res.partner"].create(
            {
                "name": "Donor Kontakt",
                "email": "donor@test.sk",
                "phone": "+421900111111",
            }
        )
        self.project_partner = self.env["res.partner"].create(
            {
                "name": "Partner Projektu",
                "email": "partner@test.sk",
                "phone": "+421900222222",
            }
        )
        self.program = self.env["tenenet.program"].create(
            {
                "name": "Program Test",
                "code": "PG_TEST",
            }
        )
        self.donor = self.env["tenenet.donor"].create(
            {
                "name": "Donor Test",
                "donor_type": "eu",
                "partner_id": self.donor_partner.id,
            }
        )
        self.employee = self.env["hr.employee"].create({"name": "Projektový Manažér"})

    def _create_user(self, login, group_ids):
        return self.env["res.users"].with_context(no_reset_password=True).create({
            "name": login,
            "login": login,
            "email": f"{login}@example.com",
            "company_id": self.env.company.id,
            "company_ids": [Command.set([self.env.company.id])],
            "group_ids": [Command.set(group_ids)],
        })

    def test_project_create_with_relations(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt A",
                "program_ids": [(4, self.program.id)],
                "donor_id": self.donor.id,
                "partner_id": self.project_partner.id,
                "odborny_garant_id": self.employee.id,
                "project_manager_id": self.employee.id,
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "semaphore": "green",
            }
        )

        self.assertIn(self.program, project.program_ids)
        self.assertIn(self.program, project.ui_program_ids)
        self.assertEqual(project.donor_id, self.donor)
        self.assertEqual(project.odborny_garant_id, self.employee)
        self.assertEqual(project.partner_id, self.project_partner)
        self.assertEqual(project.duration, 12)
        self.assertIn("donor@test.sk", project.donor_contact)
        self.assertIn("partner@test.sk", project.partner_contact)
        admin_program = self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1)
        self.assertIn(admin_program, project.program_ids)
        self.assertNotIn(admin_program, project.ui_program_ids)
        self.assertEqual(project.reporting_program_id, self.program)

    def test_project_user_role_is_read_only(self):
        base_group = self.env.ref("base.group_user")
        user_group = self.env.ref("tenenet_projects.group_tenenet_user")
        normal_user = self._create_user("project_readonly_user", [base_group.id, user_group.id])
        project = self.env["tenenet.project"].create({
            "name": "Projekt Readonly",
            "program_ids": [(4, self.program.id)],
        })

        self.assertEqual(
            self.env["tenenet.project"].with_user(normal_user).search_count([("id", "=", project.id)]),
            1,
        )
        with self.assertRaises(AccessError):
            project.with_user(normal_user).write({"description": "Blocked"})

    def test_garant_pm_uses_hidden_role_and_only_assigned_projects(self):
        base_group = self.env.ref("base.group_user")
        user_group = self.env.ref("tenenet_projects.group_tenenet_user")
        garant_group = self.env.ref("tenenet_projects.group_tenenet_garant_pm")
        pm_user = self._create_user("project_pm_hidden", [base_group.id, user_group.id])
        pm_employee = self.env["hr.employee"].create({
            "name": "PM hidden role",
            "user_id": pm_user.id,
        })
        assigned_project = self.env["tenenet.project"].create({
            "name": "Projekt assigned PM",
            "program_ids": [(4, self.program.id)],
            "project_manager_id": pm_employee.id,
        })
        other_project = self.env["tenenet.project"].create({
            "name": "Projekt not assigned PM",
            "program_ids": [(4, self.program.id)],
        })

        pm_user.invalidate_recordset(["group_ids"])
        self.assertIn(garant_group, pm_user.group_ids)
        self.assertNotIn(user_group, pm_user.group_ids)
        self.assertEqual(
            self.env["tenenet.project"].with_user(pm_user).search_count([("id", "=", assigned_project.id)]),
            1,
        )
        self.assertEqual(
            self.env["tenenet.project"].with_user(pm_user).search_count([("id", "=", other_project.id)]),
            0,
        )

        assigned_project.with_user(pm_user).write({"description": "Allowed"})
        with self.assertRaises(AccessError):
            other_project.with_user(pm_user).write({"description": "Blocked"})

        assigned_project.write({"project_manager_id": False})
        pm_user.invalidate_recordset(["group_ids"])
        self.assertNotIn(garant_group, pm_user.group_ids)

    def test_manager_role_survives_project_appointment(self):
        base_group = self.env.ref("base.group_user")
        manager_group = self.env.ref("tenenet_projects.group_tenenet_manager")
        garant_group = self.env.ref("tenenet_projects.group_tenenet_garant_pm")
        manager_user = self._create_user("project_manager_kept", [base_group.id, manager_group.id])
        manager_employee = self.env["hr.employee"].create({
            "name": "Manager stays manager",
            "user_id": manager_user.id,
        })

        self.env["tenenet.project"].create({
            "name": "Projekt manager stays manager",
            "program_ids": [(4, self.program.id)],
            "odborny_garant_id": manager_employee.id,
            "project_manager_id": manager_employee.id,
        })

        manager_user.invalidate_recordset(["group_ids"])
        self.assertIn(manager_group, manager_user.group_ids)
        self.assertNotIn(garant_group, manager_user.group_ids)

    def test_reporting_program_is_auto_resolved_from_visible_programs(self):
        second_program = self.env["tenenet.program"].create({"name": "Program B", "code": "PG_B"})
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt Programy",
                "program_ids": [(4, self.program.id)],
            }
        )

        self.assertEqual(project.reporting_program_id, self.program)

        project.write({"primary_program_id": second_program.id})

        self.assertEqual(project.primary_program_id, second_program)
        self.assertEqual(project.reporting_program_id, second_program)
        self.assertEqual(project.ui_program_ids, second_program)

    def test_project_budget_total_compute(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt B",
                "program_ids": [(4, self.program.id)],
                "donor_id": self.donor.id,
            }
        )

        self.env["tenenet.project.receipt"].create([
            {"project_id": project.id, "date_received": "2024-03-01", "amount": 500.0},
            {"project_id": project.id, "date_received": "2025-03-01", "amount": 600.0},
            {"project_id": project.id, "date_received": "2026-03-01", "amount": 700.0},
        ])
        self.assertEqual(project.budget_total, 1800.0)

    def test_project_semaphore_selection(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt D",
                "program_ids": [(4, self.program.id)],
                "donor_id": self.donor.id,
                "semaphore": "orange",
            }
        )

        self.assertEqual(project.semaphore, "orange")

    def test_project_active_year_range_from_dates(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt E",
                "program_ids": [(4, self.program.id)],
                "donor_id": self.donor.id,
                "date_start": "2024-02-01",
                "date_end": "2026-11-30",
            }
        )

        self.assertEqual(project.active_year_from, 2024)
        self.assertEqual(project.active_year_to, 2026)

    def test_project_write_still_works_without_removed_notes_field(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt F",
                "program_ids": [(4, self.program.id)],
                "donor_id": self.donor.id,
            }
        )

        project.write(
            {
                "partner_id": self.project_partner.id,
                "portal": "https://portal.test",
            }
        )

        self.assertEqual(project.partner_id, self.project_partner)
        self.assertEqual(project.portal, "https://portal.test")

    def test_admin_tenenet_seed_exists(self):
        admin_program = self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1)
        admin_project = self.env["tenenet.project"].with_context(active_test=False).search(
            [("is_tenenet_internal", "=", True)],
            limit=1,
        )

        self.assertTrue(admin_program)
        self.assertTrue(admin_project)
        self.assertEqual(admin_project.reporting_program_id, admin_program)
        self.assertIn(admin_program, admin_project.program_ids)

        action = self.env.ref("tenenet_projects.action_tenenet_project").read()[0]
        self.assertEqual(action["domain"], "[('is_tenenet_internal', '=', False)]")
        program_action = self.env.ref("tenenet_projects.action_tenenet_program").read()[0]
        self.assertEqual(
            program_action["domain"],
            "['&', ('is_tenenet_internal', '=', False), ('code', '!=', 'ADMIN_TENENET')]",
        )

    def test_assignment_wizard_returns_explicit_program_id_domain(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt Wizard",
                "program_ids": [(4, self.program.id)],
                "reporting_program_id": self.program.id,
                "donor_id": self.donor.id,
            }
        )
        wizard = self.env["tenenet.project.assignment.wizard"].new({
            "project_id": project.id,
        })

        result = wizard._onchange_project_id()

        self.assertEqual(wizard.available_program_ids.ids, project.ui_program_ids.ids)
        self.assertEqual(wizard.program_id._origin.id, self.program.id)
        self.assertEqual(
            result["domain"]["program_id"],
            [("id", "in", project.ui_program_ids.ids)],
        )

    def test_project_type_controls_international_and_admin_routing(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Medzinárodný projekt",
                "project_type": "medzinarodny",
                "program_ids": [(4, self.program.id)],
            }
        )

        admin_program = self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1)

        self.assertTrue(project._is_international_by_donor())
        self.assertFalse(project.primary_program_id)
        self.assertEqual(project.reporting_program_id, admin_program)
        self.assertEqual(project.ui_program_ids.ids, [])

    def test_project_type_requires_single_visible_program_for_narodny(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Národný projekt",
                "program_ids": [(4, self.program.id)],
            }
        )

        self.assertEqual(project.project_type, "narodny")
        self.assertEqual(project.primary_program_id, self.program)
        with self.assertRaises(ValidationError):
            self.env["tenenet.project"].create({
                "name": "Národný projekt bez programu",
                "project_type": "narodny",
            })

    def test_non_international_project_can_use_admin_tenenet_as_primary_program(self):
        admin_program = self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1)
        project = self.env["tenenet.project"].create(
            {
                "name": "Administratívny národný projekt",
                "project_type": "narodny",
                "program_ids": [Command.set(admin_program.ids)],
            }
        )

        self.assertFalse(project._is_international_by_donor())
        self.assertEqual(project.primary_program_id, admin_program)
        self.assertEqual(project.reporting_program_id, admin_program)
        self.assertEqual(project.ui_program_ids, admin_program)
        self.assertEqual(project.program_ids, admin_program)

    def test_project_budget_lines_validate_program_membership(self):
        other_program = self.env["tenenet.program"].create({"name": "Iný program", "code": "PG_OTHER"})
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt Rozpočet",
                "program_ids": [(4, self.program.id)],
                "donor_id": self.donor.id,
            }
        )

        self.env["tenenet.project.budget.line"].create({
            "project_id": project.id,
            "year": 2026,
            "budget_type": "labor",
            "program_id": self.program.id,
            "name": "Mzdy",
            "amount": 500.0,
        })
        self.assertEqual(project.budget_labor_total, 500.0)

        with self.assertRaises(ValidationError):
            self.env["tenenet.project.budget.line"].create({
                "project_id": project.id,
                "year": 2026,
                "budget_type": "pausal",
                "program_id": other_program.id,
                "name": "Paušál",
                "amount": 100.0,
            })

    def test_project_budget_type_lists_are_separated(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt Rozdelenie Rozpočtu",
                "program_ids": [(4, self.program.id)],
                "reporting_program_id": self.program.id,
                "donor_id": self.donor.id,
            }
        )
        labor_line = self.env["tenenet.project.budget.line"].create({
            "project_id": project.id,
            "year": 2026,
            "budget_type": "labor",
            "program_id": self.program.id,
            "name": "Mzdy",
            "amount": 600.0,
        })

        self.assertFalse(project.budget_pausal_line_ids)
        self.assertEqual(project.budget_labor_line_ids, labor_line)
        self.assertFalse(project.budget_other_line_ids)

    def test_project_budget_wizard_limits_available_amount(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt Wizard",
                "program_ids": [(4, self.program.id)],
                "reporting_program_id": self.program.id,
                "donor_id": self.donor.id,
            }
        )
        self.env["tenenet.project.receipt"].create({
            "project_id": project.id,
            "date_received": "2026-03-01",
            "amount": 500.0,
        })
        wizard = self.env["tenenet.project.budget.wizard"].create({
            "project_id": project.id,
            "year": 2026,
            "budget_type": "labor",
            "program_id": self.program.id,
            "name": "Mzda",
            "amount": 200.0,
        })
        self.assertAlmostEqual(wizard.available_amount, 500.0, places=2)
        wizard.action_confirm()
        self.assertEqual(project.budget_labor_total, 200.0)

        wizard_over = self.env["tenenet.project.budget.wizard"].create({
            "project_id": project.id,
            "year": 2026,
            "budget_type": "other",
            "program_id": self.program.id,
            "name": "Iné",
            "amount": 400.0,
        })
        with self.assertRaises(ValidationError):
            wizard_over.action_confirm()

    def test_project_budget_wizard_syncs_percentage_and_amount(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt Wizard Percentá",
                "program_ids": [(4, self.program.id)],
                "reporting_program_id": self.program.id,
                "donor_id": self.donor.id,
            }
        )
        self.env["tenenet.project.receipt"].create({
            "project_id": project.id,
            "date_received": "2026-02-01",
            "amount": 1000.0,
        })

        wizard = self.env["tenenet.project.budget.wizard"].new({
            "project_id": project.id,
            "year": 2026,
            "budget_type": "pausal",
            "program_id": self.program.id,
            "name": "Paušál",
        })
        wizard.allocation_percentage = 40.0
        wizard._onchange_allocation_percentage()
        self.assertAlmostEqual(wizard.amount, 400.0, places=2)

        wizard.amount = 250.0
        wizard._onchange_amount()
        self.assertAlmostEqual(wizard.allocation_percentage, 25.0, places=2)

    def test_project_allocation_summary_respects_single_visible_program_rules(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt Alokácia",
                "program_ids": [(6, 0, [self.program.id])],
                "reporting_program_id": self.program.id,
                "donor_id": self.donor.id,
            }
        )
        employee_b = self.env["hr.employee"].create({"name": "Zamestnanec B", "work_ratio": 100.0})
        self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": project.id,
            "program_id": self.program.id,
            "allocation_ratio": 60.0,
        })
        self.env["tenenet.project.assignment"].create({
            "employee_id": employee_b.id,
            "project_id": project.id,
            "program_id": self.program.id,
            "allocation_ratio": 40.0,
        })

        rows = project._get_current_program_allocation_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["program"], self.program)
        self.assertAlmostEqual(rows[0]["allocation_pct"], 100.0, places=2)

    def test_admin_program_has_no_allocation_percentage(self):
        admin_program = self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1)
        self.assertIn(admin_program.allocation_pct, (False, 0.0))
        self.assertIn(admin_program.allocation_pct_percentage, (False, 0.0))

    def test_finance_kpis_use_cashflow_plan_to_date_and_total_income(self):
        project = self.env["tenenet.project"].create(
            {
                "name": "Projekt KPI",
                "program_ids": [(4, self.program.id)],
                "reporting_program_id": self.program.id,
                "donor_id": self.donor.id,
            }
        )
        year = fields.Date.context_today(self).year
        receipt = self.env["tenenet.project.receipt"].create({
            "project_id": project.id,
            "date_received": f"{year}-02-01",
            "amount": 1000.0,
        })
        receipt.set_cashflow_month_amounts(year, {
            2: 100.0,
            3: 100.0,
            4: 133.32,
            5: 666.68,
        })
        assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": project.id,
            "program_id": self.program.id,
            "wage_hm": 1.0 / 1.362,
        })
        self.env["tenenet.project.timesheet"].create({
            "assignment_id": assignment.id,
            "period": f"{year}-02-01",
            "hours_pp": 681.0,
        })
        self.env["tenenet.project.budget.line"].create({
            "project_id": project.id,
            "year": year,
            "budget_type": "labor",
            "program_id": self.program.id,
            "name": "Plán mzdy",
            "amount": 600.0,
        })

        self.assertAlmostEqual(project.finance_actual_vs_plan_to_date_amount, -347.68, places=2)
        self.assertEqual(project.finance_actual_vs_plan_to_date_state, "minus")
        self.assertAlmostEqual(project.finance_cashflow_to_date_amount, -347.68, places=2)
        self.assertEqual(project.finance_cashflow_to_date_state, "minus")
        self.assertAlmostEqual(project.finance_forecast_total_amount, 319.0, places=2)
        self.assertEqual(project.finance_forecast_total_state, "plus")
