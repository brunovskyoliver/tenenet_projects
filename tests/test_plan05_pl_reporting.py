from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan05PLReporting(TransactionCase):
    def setUp(self):
        super().setUp()
        self.base_wage_hm = 1.0 / 1.362
        self.program_a = self.env["tenenet.program"].create(
            {
                "name": "Program A",
                "code": "PG_A",
            }
        )
        self.program_b = self.env["tenenet.program"].create(
            {
                "name": "Program B",
                "code": "PG_B",
            }
        )
        self.employee = self.env["hr.employee"].create({"name": "Zamestnanec P&L"})
        self.employee_b = self.env["hr.employee"].create({"name": "Zamestnanec P&L B"})
        self.employee_c = self.env["hr.employee"].create({"name": "Zamestnanec P&L C"})
        self.project_a = self.env["tenenet.project"].create({
            "name": "Projekt PL A",
            "program_ids": [(4, self.program_a.id)],
            "reporting_program_id": self.program_a.id,
        })
        self.project_a_2 = self.env["tenenet.project"].create({
            "name": "Projekt PL A 2",
            "program_ids": [(4, self.program_a.id)],
            "reporting_program_id": self.program_a.id,
        })
        self.project_b = self.env["tenenet.project"].create({
            "name": "Projekt PL B",
            "program_ids": [(4, self.program_b.id)],
            "reporting_program_id": self.program_b.id,
        })
        self.assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.project_a.id,
            "program_id": self.program_a.id,
            "wage_hm": self.base_wage_hm,
        })
        self.env["tenenet.project.assignment"].create([
            {
                "employee_id": self.employee_b.id,
                "project_id": self.project_a.id,
                "program_id": self.program_a.id,
                "allocation_ratio": 50.0,
                "wage_hm": self.base_wage_hm,
            },
            {
                "employee_id": self.employee_c.id,
                "project_id": self.project_a_2.id,
                "program_id": self.program_a.id,
                "allocation_ratio": 100.0,
                "wage_hm": self.base_wage_hm,
            },
            {
                "employee_id": self.employee_b.id,
                "project_id": self.project_b.id,
                "program_id": self.program_b.id,
                "allocation_ratio": 50.0,
                "wage_hm": self.base_wage_hm,
            },
        ])
        self.company = self.env.company
        base_user_group = self.env.ref("base.group_user")
        tenenet_user_group = self.env.ref("tenenet_projects.group_tenenet_user")
        tenenet_manager_group = self.env.ref("tenenet_projects.group_tenenet_manager")

        self.user_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Používateľ P&L",
                "login": "pl_user",
                "email": "pl_user@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([base_user_group.id, tenenet_user_group.id])],
            }
        )
        self.manager_user = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Manažér P&L",
                "login": "pl_manager",
                "email": "pl_manager@example.com",
                "company_id": self.company.id,
                "company_ids": [Command.set([self.company.id])],
                "group_ids": [Command.set([base_user_group.id, tenenet_manager_group.id])],
            }
        )

    def _ts(self, period, hours_pp):
        """Create a timesheet for self.assignment with wage_ccp=1.0 so total_labor_cost=hours_pp."""
        return self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment.id,
            "period": period,
            "hours_pp": hours_pp,
        })

    def _pl(self, period):
        return self.env["tenenet.pl.line"].create({
            "employee_id": self.employee.id,
            "program_id": self.program_a.id,
            "period": period,
        })

    def test_pl_line_annual_total_compute(self):
        self._ts("2025-01-01", 100.0)
        self._ts("2025-02-01", 200.0)
        self._ts("2025-03-01", 50.0)
        self._ts("2026-01-01", 75.0)

        line_jan = self._pl("2025-01-01")
        line_feb = self._pl("2025-02-01")
        line_mar = self._pl("2025-03-01")
        line_next_year = self._pl("2026-01-01")

        for line in (line_jan, line_feb, line_mar, line_next_year):
            line.invalidate_recordset()

        self.assertAlmostEqual(line_jan.annual_total, 350.0, places=2)
        self.assertAlmostEqual(line_feb.annual_total, 350.0, places=2)
        self.assertAlmostEqual(line_mar.annual_total, 350.0, places=2)
        self.assertAlmostEqual(line_next_year.annual_total, 75.0, places=2)

    def test_program_allocation_pct_sums_to_one(self):
        programs = self.env["tenenet.program"].search([])
        programs.invalidate_recordset(["allocation_pct"])
        total = sum(programs.mapped("allocation_pct"))
        self.assertAlmostEqual(total, 1.0, places=4)

    def test_reporting_fte_uses_reporting_program_assignments(self):
        self.program_a.invalidate_recordset(["reporting_fte", "operating_allocation_pct"])
        self.program_b.invalidate_recordset(["reporting_fte", "operating_allocation_pct"])

        self.assertAlmostEqual(self.program_a.reporting_fte, 2.5, places=2)
        self.assertAlmostEqual(self.program_b.reporting_fte, 0.5, places=2)
        self.assertAlmostEqual(
            self.program_a.operating_allocation_pct + self.program_b.operating_allocation_pct,
            1.0,
            places=4,
        )

    def test_pl_line_unique_constraint(self):
        self.env["tenenet.pl.line"].create({
            "employee_id": self.employee.id,
            "program_id": self.program_a.id,
            "period": "2025-04-01",
        })

        with self.cr.savepoint():
            with self.assertRaises(IntegrityError):
                self.env["tenenet.pl.line"].create({
                    "employee_id": self.employee.id,
                    "program_id": self.program_a.id,
                    "period": "2025-04-01",
                })

    def test_pl_line_acl_user_read_only_manager_full(self):
        with self.assertRaises(AccessError):
            self.env["tenenet.pl.line"].with_user(self.user_user).create({
                "employee_id": self.employee.id,
                "program_id": self.program_a.id,
                "period": "2025-05-01",
            })

        line = self.env["tenenet.pl.line"].with_user(self.manager_user).create({
            "employee_id": self.employee.id,
            "program_id": self.program_a.id,
            "period": "2025-05-01",
        })

        self.assertTrue(line.exists())

    def test_service_budget_rows_flow_into_non_admin_pl_sections(self):
        service_project = self.env["tenenet.project"].create({
            "name": "Projekt Služby",
            "project_type": "sluzby",
            "program_ids": [(4, self.program_a.id)],
        })
        lines = self.env["tenenet.project.budget.line"].create([
            {
                "project_id": service_project.id,
                "year": 2025,
                "budget_type": "labor",
                "program_id": self.program_a.id,
                "name": "Mzdy služby",
                "amount": 300.0,
            },
            {
                "project_id": service_project.id,
                "year": 2025,
                "budget_type": "other",
                "program_id": self.program_a.id,
                "name": "Tržby služby",
                "amount": 200.0,
                "service_income_type": "sales_individual",
                "can_cover_payroll": True,
            },
        ])
        lines[0].set_month_amounts({"1": 300.0})
        lines[1].set_month_amounts({"1": 200.0})

        values = self.env["tenenet.pl.report.handler"]._get_program_report_values(self.program_a, 2025)

        self.assertAlmostEqual(values["sales_individual"]["values"][1], 200.0, places=2)
        self.assertAlmostEqual(values["budget_labor_income_total"]["values"][1], 300.0, places=2)
        self.assertAlmostEqual(values["labor_coverage"]["values"][1], 500.0, places=2)
