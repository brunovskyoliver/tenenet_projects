from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan05PLReporting(TransactionCase):
    def setUp(self):
        super().setUp()
        self.program_a = self.env["tenenet.program"].create(
            {
                "name": "Program A",
                "code": "PG_A",
                "headcount": 3.0,
            }
        )
        self.program_b = self.env["tenenet.program"].create(
            {
                "name": "Program B",
                "code": "PG_B",
                "headcount": 1.0,
            }
        )
        self.employee = self.env["hr.employee"].create({"name": "Zamestnanec P&L"})
        self.project_a = self.env["tenenet.project"].create({
            "name": "Projekt PL A",
            "program_ids": [(4, self.program_a.id)],
        })
        self.assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.project_a.id,
            "wage_hm": 0.0,
            "wage_ccp": 1.0,
        })
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
        self.program_a.invalidate_recordset(["allocation_pct"])
        self.program_b.invalidate_recordset(["allocation_pct"])
        total = self.program_a.allocation_pct + self.program_b.allocation_pct
        self.assertAlmostEqual(self.program_a.allocation_pct, 0.75, places=4)
        self.assertAlmostEqual(self.program_b.allocation_pct, 0.25, places=4)
        self.assertAlmostEqual(total, 1.0, places=4)

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
