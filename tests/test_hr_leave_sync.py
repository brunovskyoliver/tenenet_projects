from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHrLeaveSync(TransactionCase):
    def setUp(self):
        super().setUp()
        self.leave_model = self.env["hr.leave"]
        self.leave_rule_model = self.env["tenenet.project.leave.rule"]
        self.sync_model = self.env["tenenet.project.leave.sync.entry"]
        self.internal_expense_model = self.env["tenenet.internal.expense"]

        self.employee = self.env["hr.employee"].create({
            "name": "Adam Zamestnanec",
            "hourly_rate": 11.0,
            "work_ratio": 100.0,
        })
        self.employee_2 = self.env["hr.employee"].create({
            "name": "Beata Zamestnanec",
            "hourly_rate": 12.0,
            "work_ratio": 100.0,
        })

        self.project_a = self.env["tenenet.project"].create({"name": "Projekt A"})
        self.project_b = self.env["tenenet.project"].create({"name": "Projekt B"})
        self.assignment_a = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.project_a.id,
            "allocation_ratio": 40.0,
            "wage_hm": 11.0,
        })
        self.assignment_b = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.project_b.id,
            "allocation_ratio": 40.0,
            "wage_hm": 13.0,
        })

    def _create_leave_type(self, name, tenenet_hour_type=False):
        vals = {
            "name": name,
            "time_type": "leave",
            "request_unit": "day",
            "leave_validation_type": "manager",
            "allocation_validation_type": "no_validation",
            "requires_allocation": False,
            "employee_requests": True,
        }
        if tenenet_hour_type:
            vals["tenenet_hour_type"] = tenenet_hour_type
        return self.env["hr.leave.type"].create(vals)

    def _create_leave_rule(self, project, leave_type, max_days=0.0):
        return self.leave_rule_model.create({
            "project_id": project.id,
            "leave_type_id": leave_type.id,
            "included": True,
            "max_leaves_per_year_days": max_days,
        })

    def _create_leave(self, employee, leave_type, request_date_from, request_date_to=None, **overrides):
        vals = {
            "employee_id": employee.id,
            "holiday_status_id": leave_type.id,
            "request_date_from": request_date_from,
            "request_date_to": request_date_to or request_date_from,
        }
        if overrides.get("tenenet_override_assignment_id"):
            vals["tenenet_override_assignment_id"] = overrides["tenenet_override_assignment_id"].id
        if overrides.get("tenenet_override_is_internal"):
            vals["tenenet_override_is_internal"] = True
        return self.leave_model.create(vals)

    def _approve_leave(self, leave):
        leave.action_approve()
        leave.invalidate_recordset()
        self.assertEqual(leave.state, "validate")
        return leave

    def _sync_entries_for_leave(self, leave):
        return self.sync_model.search([("leave_id", "=", leave.id)])

    def _internal_expenses_for_leave(self, leave):
        return self.internal_expense_model.search([("leave_id", "=", leave.id)])

    def test_unmapped_leave_approval_creates_internal_expense_with_best_fit_source(self):
        leave_type = self._create_leave_type("Voľné dni z dôvodu nevoľnosti")
        self._create_leave_rule(self.project_a, leave_type)
        self._create_leave_rule(self.project_b, leave_type)

        first_leave = self._approve_leave(self._create_leave(
            self.employee,
            leave_type,
            "2026-01-12",
            tenenet_override_assignment_id=self.assignment_a,
        ))
        first_internal = self._internal_expenses_for_leave(first_leave)
        self.assertEqual(first_internal.source_assignment_id, self.assignment_a)
        self.assertFalse(first_internal.hour_type)
        self.assertFalse(self._sync_entries_for_leave(first_leave))

        auto_leave = self._approve_leave(self._create_leave(
            self.employee,
            leave_type,
            "2026-02-10",
        ))
        auto_internal = self._internal_expenses_for_leave(auto_leave)

        self.assertEqual(auto_internal.source_assignment_id, self.assignment_b)
        self.assertFalse(auto_internal.hour_type)
        self.assertFalse(self._sync_entries_for_leave(auto_leave))

    def test_unmapped_leave_manual_override_uses_source_assignment_without_sync(self):
        leave_type = self._create_leave_type("Voľné dni z dôvodu nevoľnosti")
        self._create_leave_rule(self.project_a, leave_type)

        leave = self._approve_leave(self._create_leave(
            self.employee,
            leave_type,
            "2026-03-10",
            tenenet_override_assignment_id=self.assignment_a,
        ))
        internal_expense = self._internal_expenses_for_leave(leave)

        self.assertEqual(internal_expense.source_assignment_id, self.assignment_a)
        self.assertFalse(internal_expense.hour_type)
        self.assertFalse(self._sync_entries_for_leave(leave))
        self.assertFalse(self.env["tenenet.project.timesheet"].search([
            ("assignment_id", "=", self.assignment_a.id),
            ("period", "=", "2026-03-01"),
        ]))

    def test_mapped_leave_allocates_to_least_used_assignment(self):
        leave_type = self._create_leave_type("Dovolenka test", tenenet_hour_type="vacation")
        self._create_leave_rule(self.project_a, leave_type)
        self._create_leave_rule(self.project_b, leave_type)

        self._approve_leave(self._create_leave(
            self.employee,
            leave_type,
            "2026-01-13",
            tenenet_override_assignment_id=self.assignment_a,
        ))
        leave = self._approve_leave(self._create_leave(
            self.employee,
            leave_type,
            "2026-02-10",
        ))
        sync_entry = self._sync_entries_for_leave(leave)

        self.assertEqual(sync_entry.assignment_id, self.assignment_b)
        self.assertFalse(self._internal_expenses_for_leave(leave))

    def test_mapped_leave_tie_breaks_to_lowest_assignment_id(self):
        leave_type = self._create_leave_type("Dovolenka remiza", tenenet_hour_type="vacation")
        self._create_leave_rule(self.project_a, leave_type)
        self._create_leave_rule(self.project_b, leave_type)

        leave = self._approve_leave(self._create_leave(
            self.employee,
            leave_type,
            "2026-04-10",
        ))
        sync_entry = self._sync_entries_for_leave(leave)

        self.assertEqual(sync_entry.assignment_id, min(self.assignment_a | self.assignment_b, key=lambda rec: rec.id))
        self.assertFalse(self._internal_expenses_for_leave(leave))

    def test_mapped_leave_refreshes_matrix_storage_without_opening_grid(self):
        leave_type = self._create_leave_type("Dovolenka matica", tenenet_hour_type="vacation")
        self._create_leave_rule(self.project_a, leave_type)
        matrix = self.env["tenenet.project.timesheet.matrix"].create({
            "assignment_id": self.assignment_a.id,
            "year": 2026,
        })
        vacation_row = matrix.line_ids.filtered(lambda line: line.hour_type == "vacation")[:1]
        vacation_entry = vacation_row.entry_ids.filtered(
            lambda entry: entry.period == fields.Date.to_date("2026-05-01")
        )[:1]

        self.assertAlmostEqual(vacation_row.month_05, 0.0)
        self.assertAlmostEqual(vacation_entry.hours, 0.0)

        self._approve_leave(self._create_leave(
            self.employee,
            leave_type,
            "2026-05-14",
            tenenet_override_assignment_id=self.assignment_a,
        ))

        vacation_row.invalidate_recordset(["month_05"])
        vacation_entry.invalidate_recordset(["hours"])
        self.assertAlmostEqual(vacation_row.month_05, 8.0)
        self.assertAlmostEqual(vacation_entry.hours, 8.0)

    def test_leave_limit_is_per_employee_and_over_limit_goes_internal(self):
        leave_type = self._create_leave_type("Lekár test", tenenet_hour_type="doctor")
        shared_project = self.env["tenenet.project"].create({"name": "Projekt Shared"})
        assignment_emp1 = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": shared_project.id,
            "allocation_ratio": 20.0,
            "wage_hm": 15.0,
        })
        assignment_emp2 = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee_2.id,
            "project_id": shared_project.id,
            "allocation_ratio": 20.0,
            "wage_hm": 16.0,
        })
        self._create_leave_rule(shared_project, leave_type, max_days=1.0)

        first_emp1 = self._approve_leave(self._create_leave(
            self.employee,
            leave_type,
            "2026-05-11",
            tenenet_override_assignment_id=assignment_emp1,
        ))
        first_emp2 = self._approve_leave(self._create_leave(
            self.employee_2,
            leave_type,
            "2026-05-12",
        ))
        second_emp1 = self._approve_leave(self._create_leave(
            self.employee,
            leave_type,
            "2026-05-13",
        ))

        self.assertEqual(self._sync_entries_for_leave(first_emp1).assignment_id, assignment_emp1)
        self.assertEqual(self._sync_entries_for_leave(first_emp2).assignment_id, assignment_emp2)
        self.assertFalse(self._sync_entries_for_leave(second_emp1))
        self.assertEqual(self._internal_expenses_for_leave(second_emp1).source_assignment_id, assignment_emp1)

    def test_leave_without_matching_rule_goes_to_internal_expense(self):
        leave_type = self._create_leave_type("Náhradné voľno test", tenenet_hour_type="vacation")

        leave = self._approve_leave(self._create_leave(
            self.employee,
            leave_type,
            "2026-06-10",
        ))
        internal_expense = self._internal_expenses_for_leave(leave)

        self.assertFalse(self._sync_entries_for_leave(leave))
        self.assertEqual(internal_expense.source_assignment_id, self.assignment_a)
        self.assertEqual(internal_expense.period, fields.Date.to_date("2026-06-01"))
