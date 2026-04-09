from datetime import date

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetProjectRecurringClone(TransactionCase):
    def setUp(self):
        super().setUp()
        self.program = self.env["tenenet.program"].create({
            "name": "Licenčný program",
            "code": "LIC_TEST",
        })
        self.partner = self.env["res.partner"].create({"name": "Partner"})
        self.recipient = self.env["res.partner"].create({"name": "TENENET o.z."})
        self.donor = self.env["tenenet.donor"].create({"name": "Donor"})
        self.manager = self.env["hr.employee"].create({"name": "Projektový manažér"})
        self.employee = self.env["hr.employee"].create({
            "name": "Zamestnanec projektu",
            "parent_id": self.manager.id,
            "work_ratio": 100.0,
        })
        self.site = self.env["tenenet.project.site"].create({
            "name": "Bratislava",
            "site_type": "prevadzka",
        })
        self.contact = self.env["tenenet.project.contact"].create({
            "name": "Projektový kontakt",
        })
        self.leave_type = self.env["hr.leave.type"].create({"name": "Dovolenka test"})
        base_user_group = self.env.ref("base.group_user")
        tenenet_manager_group = self.env.ref("tenenet_projects.group_tenenet_manager")
        self.manager_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Tenenet manažér",
            "login": "recurring.clone.manager",
            "email": "recurring.clone.manager@example.com",
            "company_id": self.env.company.id,
            "company_ids": [Command.set([self.env.company.id])],
            "group_ids": [Command.set([base_user_group.id, tenenet_manager_group.id])],
        })

    def _create_recurring_project(self, **overrides):
        vals = {
            "name": "Licenčný projekt",
            "program_ids": [Command.link(self.program.id)],
            "reporting_program_id": self.program.id,
            "donor_id": self.donor.id,
            "partner_id": self.partner.id,
            "recipient_partner_id": self.recipient.id,
            "odborny_garant_id": self.manager.id,
            "project_manager_id": self.manager.id,
            "date_start": "2026-01-01",
            "date_end": "2026-12-31",
            "is_recurring_license_project": True,
            "site_ids": [Command.link(self.site.id)],
            "contact_ids": [Command.link(self.contact.id)],
        }
        vals.update(overrides)
        return self.env["tenenet.project"].create(vals)

    def test_recurring_defaults_anchor_to_year_end(self):
        project = self._create_recurring_project(date_end="2026-05-10")

        self.assertTrue(project.is_recurring_license_project)
        self.assertEqual(project.recurring_clone_interval_type, "years")
        self.assertEqual(project.recurring_clone_anchor_date, date(2026, 12, 31))
        self.assertEqual(project.recurring_next_clone_date, date(2026, 12, 31))
        self.assertEqual(project.recurring_root_project_id, project)
        self.assertEqual(project.recurring_base_name, "Licenčný projekt")

    def test_manual_clone_copies_forecast_inputs_but_not_actuals(self):
        project = self._create_recurring_project()
        self.env["tenenet.project.leave.rule"].create({
            "project_id": project.id,
            "leave_type_id": self.leave_type.id,
            "included": True,
            "max_leaves_per_year_days": 5.0,
        })
        allowed_type = self.env["tenenet.project.allowed.expense.type"].create({
            "project_id": project.id,
            "name": "Materiál",
            "max_amount": 500.0,
        })
        self.env["tenenet.project.budget.line"].create({
            "project_id": project.id,
            "year": 2026,
            "budget_type": "labor",
            "program_id": self.program.id,
            "name": "Mzdy",
            "amount": 1200.0,
        })
        self.env["tenenet.project.milestone"].with_user(self.manager_user).create({
            "project_id": project.id,
            "name": "Odovzdanie",
            "date": "2026-09-01",
        })
        receipt = self.env["tenenet.project.receipt"].create({
            "project_id": project.id,
            "date_received": "2026-03-15",
            "amount": 1200.0,
            "note": "Ročný príjem",
        })
        receipt.set_cashflow_month_amounts(2026, {3: 900.0, 9: 300.0})
        assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": project.id,
            "program_id": self.program.id,
            "site_ids": [Command.set([self.site.id])],
            "date_start": "2026-01-01",
            "date_end": "2026-12-31",
            "allocation_ratio": 50.0,
            "wage_hm": 10.0,
        })
        march_timesheet = assignment.timesheet_ids.filtered(lambda rec: rec.period == date(2026, 3, 1))
        march_timesheet.write({"hours_pp": 8.0})
        self.env["tenenet.project.expense"].create({
            "project_id": project.id,
            "allowed_type_id": allowed_type.id,
            "date": "2026-04-10",
            "amount": 90.0,
            "description": "Skutočný výdavok",
        })

        action = project.action_test_recurring_clone()
        cloned_project = self.env["tenenet.project"].browse(action["res_id"])

        self.assertEqual(action["res_model"], "tenenet.project")
        self.assertTrue(cloned_project.exists())
        self.assertEqual(cloned_project.name, "Licenčný projekt 2027")
        self.assertTrue(cloned_project.active)
        self.assertEqual(cloned_project.date_start, date(2027, 1, 1))
        self.assertEqual(cloned_project.date_end, date(2027, 12, 31))
        self.assertEqual(cloned_project.site_ids, self.site)
        self.assertEqual(cloned_project.contact_ids, self.contact)
        self.assertEqual(cloned_project.leave_rule_ids.leave_type_id, self.leave_type)
        self.assertEqual(cloned_project.allowed_expense_type_ids.name, "Materiál")
        self.assertEqual(cloned_project.budget_line_ids.year, 2027)
        self.assertEqual(cloned_project.milestone_ids.date, date(2027, 9, 1))
        self.assertEqual(cloned_project.receipt_line_ids.date_received, date(2027, 3, 15))
        self.assertEqual(sum(cloned_project.cashflow_ids.mapped("amount")), 1200.0)
        self.assertEqual(
            {
                cashflow.month: cashflow.amount
                for cashflow in cloned_project.cashflow_ids.sorted("month")
            },
            {3: 900.0, 9: 300.0},
        )
        self.assertFalse(cloned_project.expense_ids)
        self.assertEqual(sum(cloned_project.timesheet_ids.mapped("hours_total")), 0.0)
        self.assertEqual(cloned_project.assignment_ids.employee_id, self.employee)
        self.assertEqual(cloned_project.assignment_ids.site_ids, self.site)
        self.assertEqual(project.recurring_last_clone_date, date(2026, 12, 31))
        self.assertEqual(project.recurring_next_clone_date, date(2027, 12, 31))

    def test_second_clone_uses_latest_project_in_chain(self):
        project = self._create_recurring_project()
        first_clone = project.action_test_recurring_clone() and self.env["tenenet.project"].search([
            ("recurring_root_project_id", "=", project.id),
        ], order="id desc", limit=1)
        first_clone.write({"description": "Prenesené z prvého klonu"})
        self.env["tenenet.project.receipt"].create({
            "project_id": first_clone.id,
            "date_received": "2027-06-01",
            "amount": 300.0,
            "note": "Doplnené v prvom klone",
        })

        second_action = project.action_test_recurring_clone()
        second_clone = self.env["tenenet.project"].browse(second_action["res_id"])

        self.assertEqual(second_clone.description, "Prenesené z prvého klonu")
        self.assertEqual(len(second_clone.receipt_line_ids), 1)
        self.assertEqual(second_clone.receipt_line_ids.date_received, date(2028, 6, 1))
        self.assertEqual(project.recurring_source_project_id, first_clone)
        self.assertEqual(project.recurring_next_clone_date, date(2028, 12, 31))

    def test_archived_clone_is_ignored_as_future_source(self):
        project = self._create_recurring_project()
        first_clone = project.action_test_recurring_clone() and self.env["tenenet.project"].search([
            ("recurring_root_project_id", "=", project.id),
        ], order="id desc", limit=1)
        first_clone.write({"description": "Archivovaný klon", "active": False})

        second_action = project.action_test_recurring_clone()
        second_clone = self.env["tenenet.project"].browse(second_action["res_id"])

        self.assertNotEqual(second_clone.id, first_clone.id)
        self.assertNotEqual(project.recurring_source_project_id, first_clone)
        self.assertEqual(second_clone.description, project.description)
        self.assertTrue(second_clone.active)

    def test_cron_clones_due_project_only_once(self):
        project = self._create_recurring_project(recurring_clone_anchor_date=fields.Date.context_today(self.env["tenenet.project"]))

        self.env["tenenet.project"]._cron_run_recurring_project_clones()
        first_count = self.env["tenenet.project"].search_count([
            ("recurring_root_project_id", "=", project.id),
            ("id", "!=", project.id),
        ])

        self.env["tenenet.project"]._cron_run_recurring_project_clones()
        second_count = self.env["tenenet.project"].search_count([
            ("recurring_root_project_id", "=", project.id),
            ("id", "!=", project.id),
        ])

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)
