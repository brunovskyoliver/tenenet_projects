from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan09ProjectTimesheet(TransactionCase):
    def setUp(self):
        super().setUp()
        self.program = self.env["tenenet.program"].create({"name": "Program Timesheet", "code": "PLAN09_TS"})
        self.employee = self.env["hr.employee"].create({"name": "Zamestnanec Timesheet"})
        self.project = self.env["tenenet.project"].create({
            "name": "Projekt Timesheet",
            "program_ids": [(6, 0, self.program.ids)],
            "reporting_program_id": self.program.id,
        })
        self.project2 = self.env["tenenet.project"].create({
            "name": "Projekt Timesheet 2",
            "program_ids": [(6, 0, self.program.ids)],
            "reporting_program_id": self.program.id,
        })
        self.assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.project.id,
            "allocation_ratio": 50.0,
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        })
        self.assignment2 = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.project2.id,
            "allocation_ratio": 50.0,
            "wage_hm": 12.0,
            "wage_ccp": 16.0,
        })

    def _timesheet_vals(self, assignment=None, **overrides):
        vals = {
            "assignment_id": (assignment or self.assignment).id,
            "period": "2026-01-01",
            "hours_pp": 80.0,
            "hours_np": 20.0,
            "hours_vacation": 0.0,
        }
        vals.update(overrides)
        return vals

    def test_computed_hour_totals(self):
        ts = self.env["tenenet.project.timesheet"].with_context(from_hr_leave_sync=True).create(self._timesheet_vals(
            hours_pp=80.0,
            hours_np=20.0,
            hours_travel=5.0,
            hours_training=3.0,
            hours_ambulance=0.0,
            hours_international=0.0,
            hours_vacation=10.0,
            hours_sick=5.0,
            hours_doctor=3.0,
            hours_holidays=8.0,
        ))
        self.assertAlmostEqual(ts.hours_project_total, 108.0)
        self.assertAlmostEqual(ts.hours_leave_total, 26.0)
        self.assertAlmostEqual(ts.hours_total, 134.0)
        self.assertEqual(set(ts.line_ids.mapped("hour_type")), {
            "pp", "np", "travel", "training", "vacation", "sick", "doctor", "holidays",
        })

    def test_hour_lines_aggregate_back_to_parent(self):
        ts = self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment.id,
            "period": "2026-04-01",
        })
        self.env["tenenet.project.timesheet.line"].with_context(from_hr_leave_sync=True).create([
            {
                "timesheet_id": ts.id,
                "hour_type": "pp",
                "hours": 16.0,
            },
            {
                "timesheet_id": ts.id,
                "hour_type": "np",
                "hours": 8.0,
            },
            {
                "timesheet_id": ts.id,
                "hour_type": "vacation",
                "hours": 4.0,
            },
        ])
        ts.invalidate_recordset()
        self.assertAlmostEqual(ts.hours_pp, 16.0)
        self.assertAlmostEqual(ts.hours_np, 8.0)
        self.assertAlmostEqual(ts.hours_vacation, 4.0)
        self.assertAlmostEqual(ts.hours_project_total, 24.0)
        self.assertAlmostEqual(ts.hours_leave_total, 4.0)
        self.assertAlmostEqual(ts.hours_total, 28.0)

    def test_parent_hour_write_updates_normalized_lines(self):
        ts = self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment.id,
            "period": "2026-05-01",
        })
        ts.with_context(from_hr_leave_sync=True).write({
            "hours_pp": 12.0,
            "hours_np": 6.0,
            "hours_vacation": 2.0,
        })
        self.assertEqual(len(ts.line_ids), 3)
        self.assertAlmostEqual(
            ts.line_ids.filtered(lambda line: line.hour_type == "pp").hours,
            12.0,
        )
        self.assertAlmostEqual(
            ts.line_ids.filtered(lambda line: line.hour_type == "np").hours,
            6.0,
        )
        self.assertAlmostEqual(
            ts.line_ids.filtered(lambda line: line.hour_type == "vacation").hours,
            2.0,
        )

    def test_computed_costs(self):
        ts = self.env["tenenet.project.timesheet"].create(self._timesheet_vals(
            hours_pp=100.0,
            hours_np=0.0,
            hours_vacation=0.0,
        ))
        self.assertAlmostEqual(ts.hours_total, 100.0)
        self.assertAlmostEqual(ts.gross_salary, 1000.0, places=2)
        self.assertAlmostEqual(ts.deductions, 362.0, places=2)
        self.assertAlmostEqual(ts.total_labor_cost, 1362.0, places=2)

    def test_wage_inherited_from_assignment(self):
        ts = self.env["tenenet.project.timesheet"].create(self._timesheet_vals())
        self.assertAlmostEqual(ts.wage_hm, 10.0)
        self.assertAlmostEqual(ts.wage_ccp, 13.62)

    def test_related_fields_from_assignment(self):
        ts = self.env["tenenet.project.timesheet"].create(self._timesheet_vals())
        self.assertEqual(ts.employee_id, self.employee)
        self.assertEqual(ts.project_id, self.project)

    def test_unique_assignment_period_constraint(self):
        self.env["tenenet.project.timesheet"].create(self._timesheet_vals())
        with self.cr.savepoint():
            with self.assertRaises(IntegrityError):
                self.env["tenenet.project.timesheet"].create(self._timesheet_vals())

    def test_different_period_allowed(self):
        ts1 = self.env["tenenet.project.timesheet"].create(self._timesheet_vals(period="2026-01-01"))
        ts2 = self.env["tenenet.project.timesheet"].create(self._timesheet_vals(period="2026-02-01"))
        self.assertTrue(ts1.exists())
        self.assertTrue(ts2.exists())

    def test_zero_capacity_cost(self):
        ts = self.env["tenenet.project.timesheet"].create(self._timesheet_vals(
            hours_pp=0.0, hours_np=0.0, hours_vacation=0.0
        ))
        self.assertAlmostEqual(ts.gross_salary, 0.0)
        self.assertAlmostEqual(ts.total_labor_cost, 0.0)

    def test_zero_assignment_cap_falls_back_to_project_default(self):
        self.project.write({"default_max_monthly_wage_hm": 500.0})
        self.assignment.write({"max_monthly_wage_hm": 0.0})

        self.env["tenenet.project.timesheet"].create(self._timesheet_vals(
            hours_pp=100.0, hours_np=0.0, hours_vacation=0.0
        ))

        wage_expense = self.env["tenenet.internal.expense"].search([
            ("source_assignment_id", "=", self.assignment.id),
            ("period", "=", "2026-01-01"),
            ("category", "=", "wage"),
        ], limit=1)

        self.assertTrue(wage_expense)
        self.assertAlmostEqual(wage_expense.cost_ccp, 681.0, places=2)

    def test_tenenet_cost_residual_auto_created_and_computed(self):
        self.env["tenenet.project.timesheet"].create(self._timesheet_vals(
            hours_pp=100.0, hours_np=0.0, hours_vacation=0.0
        ))
        self.env["tenenet.project.timesheet"].create(self._timesheet_vals(
            assignment=self.assignment2, period="2026-01-01",
            hours_pp=50.0, hours_np=0.0, hours_vacation=0.0
        ))
        cost = self.env["tenenet.employee.tenenet.cost"].search([
            ("employee_id", "=", self.employee.id),
            ("period", "=", "2026-01-01"),
        ], limit=1)
        self.assertTrue(cost)
        cost.write({
            "gross_salary_employee": 2000.0,
            "total_labor_cost_employee": 2724.0,
        })
        # project billed: 100 * 10 + 50 * 12 = 1000 + 600 = 1600
        self.assertAlmostEqual(cost.project_billed_gross, 1600.0, places=2)
        self.assertAlmostEqual(cost.tenenet_residual_hm, 400.0, places=2)

    def test_residual_record_updates_when_lines_change(self):
        ts = self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment.id,
            "period": "2026-06-01",
            "hours_pp": 10.0,
        })
        cost = self.env["tenenet.employee.tenenet.cost"].search([
            ("employee_id", "=", self.employee.id),
            ("period", "=", "2026-06-01"),
        ], limit=1)
        self.assertTrue(cost)
        cost.write({
            "gross_salary_employee": 500.0,
            "total_labor_cost_employee": 700.0,
        })
        self.assertAlmostEqual(cost.project_billed_gross, 100.0, places=2)
        ts.write({"hours_pp": 20.0})
        cost.invalidate_recordset()
        self.assertAlmostEqual(cost.project_billed_gross, 200.0, places=2)

    def test_monthly_gross_target_creates_and_updates_residual_internal_expense(self):
        self.employee.write({"monthly_gross_salary_target": 900.0})
        ts = self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment.id,
            "period": "2026-07-01",
            "hours_pp": 50.0,
        })

        cost = self.env["tenenet.employee.tenenet.cost"].search([
            ("employee_id", "=", self.employee.id),
            ("period", "=", "2026-07-01"),
        ], limit=1)
        expense = self.env["tenenet.internal.expense"].search([
            ("tenenet_cost_id", "=", cost.id),
        ], limit=1)

        self.assertTrue(cost)
        self.assertTrue(expense)
        self.assertEqual(expense.category, "residual_wage")
        self.assertTrue(expense.source_project_id.is_tenenet_internal)
        self.assertFalse(expense.source_assignment_id)
        self.assertAlmostEqual(cost.project_billed_gross, 500.0, places=2)
        self.assertAlmostEqual(expense.cost_hm, 400.0, places=2)

        ts.write({"hours_pp": 90.0})
        expense.invalidate_recordset()
        self.assertFalse(expense.exists())

    def test_monthly_matrix_loads_existing_hours(self):
        self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment.id,
            "period": "2026-01-01",
            "hours_pp": 11.0,
            "hours_np": 4.0,
        })
        self.env["tenenet.project.timesheet"].with_context(from_hr_leave_sync=True).create({
            "assignment_id": self.assignment2.id,
            "period": "2026-03-01",
            "hours_vacation": 7.0,
        })

        matrix = self.env["tenenet.project.timesheet.matrix"].create({
            "assignment_id": self.assignment.id,
            "year": 2026,
        })
        row_pp = matrix.line_ids.filtered(
            lambda line: line.assignment_id == self.assignment and line.hour_type == "pp"
        )
        row_np = matrix.line_ids.filtered(
            lambda line: line.assignment_id == self.assignment and line.hour_type == "np"
        )
        self.assertTrue(row_pp)
        self.assertAlmostEqual(row_pp.month_01, 11.0)
        self.assertAlmostEqual(row_np.month_01, 4.0)

    def test_monthly_matrix_applies_hours_to_timesheets(self):
        matrix = self.env["tenenet.project.timesheet.matrix"].create({
            "assignment_id": self.assignment.id,
            "year": 2026,
        })
        row_pp = matrix.line_ids.filtered(
            lambda line: line.assignment_id == self.assignment and line.hour_type == "pp"
        )
        row_np = matrix.line_ids.filtered(
            lambda line: line.assignment_id == self.assignment and line.hour_type == "np"
        )
        row_pp.month_01 = 14.0
        row_pp.month_02 = 9.0
        row_np.month_02 = 3.0

        january = self.env["tenenet.project.timesheet"].search([
            ("assignment_id", "=", self.assignment.id),
            ("period", "=", "2026-01-01"),
        ], limit=1)
        february = self.env["tenenet.project.timesheet"].search([
            ("assignment_id", "=", self.assignment.id),
            ("period", "=", "2026-02-01"),
        ], limit=1)
        self.assertAlmostEqual(january.hours_pp, 14.0)
        self.assertAlmostEqual(february.hours_pp, 9.0)
        self.assertAlmostEqual(february.hours_np, 3.0)

    def test_assignment_precreates_monthly_timesheets_for_project_range(self):
        project = self.env["tenenet.project"].create({
            "name": "Projekt s rozsahom",
            "date_start": "2026-01-15",
            "date_end": "2026-03-05",
        })
        assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": project.id,
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        })
        self.assertEqual(
            assignment.timesheet_ids.mapped("period"),
            [
                fields.Date.to_date("2026-01-01"),
                fields.Date.to_date("2026-02-01"),
                fields.Date.to_date("2026-03-01"),
            ],
        )
        self.assertEqual(
            assignment.timesheet_ids.mapped("hours_total"),
            [0.0, 0.0, 0.0],
        )

    def test_assignment_open_matrix_current_year_creates_matrix(self):
        project = self.env["tenenet.project"].create({
            "name": "Projekt na maticu",
            "date_start": "2025-12-01",
            "date_end": "2026-12-31",
        })
        assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": project.id,
            "date_start": "2025-12-01",
            "date_end": "2026-12-31",
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        })
        action = assignment.action_open_timesheet_matrix_current_year()
        self.assertEqual(action["res_model"], "tenenet.project.timesheet.matrix.entry")
        self.assertEqual(action["view_mode"], "grid,list,form")
        self.assertEqual(action["domain"], [("matrix_id", "=", assignment.matrix_ids.filtered(lambda rec: rec.year == 2026).id)])
        matrix = self.env["tenenet.project.timesheet.matrix"].browse(action["context"]["default_matrix_id"])
        self.assertTrue(matrix)
        self.assertEqual(matrix.assignment_id, assignment)
        self.assertEqual(matrix.year, 2026)
        self.assertEqual(
            assignment.matrix_ids.mapped("year"),
            [2025, 2026],
        )
        self.assertEqual(
            action["context"]["grid_anchor"],
            "2026-01-01",
        )
        self.assertEqual(len(matrix.line_ids), 10)

    def test_matrix_grid_entries_follow_matrix_and_update_timesheets(self):
        matrix = self.env["tenenet.project.timesheet.matrix"].create({
            "assignment_id": self.assignment.id,
            "year": 2026,
        })
        row_pp = matrix.line_ids.filtered(lambda line: line.hour_type == "pp")[:1]
        entries = self.env["tenenet.project.timesheet.matrix.entry"].search([
            ("line_id", "=", row_pp.id),
        ], order="period")

        self.assertEqual(len(entries), 12)
        self.assertEqual(entries[0].period, fields.Date.to_date("2026-01-01"))
        self.assertTrue(entries[0].editable)

        january_entry = entries[0]
        self.env["tenenet.project.timesheet.matrix.entry"].grid_update_cell(
            [("id", "=", january_entry.id)],
            "hours",
            14.0,
        )

        row_pp.invalidate_recordset(["month_01"])
        self.assertAlmostEqual(row_pp.month_01, 14.0)

        january = self.env["tenenet.project.timesheet"].search([
            ("assignment_id", "=", self.assignment.id),
            ("period", "=", "2026-01-01"),
        ], limit=1)
        self.assertAlmostEqual(january.hours_pp, 14.0)

    def test_matrix_grid_leave_entries_are_locked(self):
        matrix = self.env["tenenet.project.timesheet.matrix"].create({
            "assignment_id": self.assignment.id,
            "year": 2026,
        })
        leave_entry = self.env["tenenet.project.timesheet.matrix.entry"].search([
            ("matrix_id", "=", matrix.id),
            ("hour_type", "=", "doctor"),
            ("period", "=", "2026-01-01"),
        ], limit=1)
        self.assertTrue(leave_entry)
        self.assertFalse(leave_entry.editable)

        with self.assertRaises(ValidationError):
            self.env["tenenet.project.timesheet.matrix.entry"].grid_update_cell(
                [("id", "=", leave_entry.id)],
                "hours",
                2.0,
            )

    def test_open_ended_assignment_creates_year_matrices_until_present(self):
        project = self.env["tenenet.project"].create({
            "name": "Projekt bez konca",
        })
        assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": project.id,
            "date_start": "2025-06-01",
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        })
        self.assertEqual(
            assignment.matrix_ids.mapped("year"),
            [2025, 2026],
        )

    def test_matrix_write_keeps_other_month_values(self):
        matrix = self.env["tenenet.project.timesheet.matrix"].create({
            "assignment_id": self.assignment.id,
            "year": 2026,
        })
        row_pp = matrix.line_ids.filtered(
            lambda line: line.assignment_id == self.assignment and line.hour_type == "pp"
        )
        row_pp.write({
            "month_01": 4.0,
            "month_02": 5.0,
        })
        row_pp.invalidate_recordset(["month_01", "month_02"])
        self.assertAlmostEqual(row_pp.month_01, 4.0)
        self.assertAlmostEqual(row_pp.month_02, 5.0)

        row_pp.write({
            "month_03": 6.0,
        })
        row_pp.invalidate_recordset(["month_01", "month_02", "month_03"])
        self.assertAlmostEqual(row_pp.month_01, 4.0)
        self.assertAlmostEqual(row_pp.month_02, 5.0)
        self.assertAlmostEqual(row_pp.month_03, 6.0)

    def test_matrix_months_outside_assignment_range_are_locked(self):
        project = self.env["tenenet.project"].create({
            "name": "Projekt s hranicami matice",
            "date_start": "2025-12-01",
            "date_end": "2026-12-31",
        })
        assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": project.id,
            "date_start": "2025-12-01",
            "date_end": "2026-12-31",
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        })
        assignment.action_open_timesheet_matrix_current_year()
        matrix_2025 = assignment.matrix_ids.filtered(lambda rec: rec.year == 2025)
        row_pp = matrix_2025.line_ids.filtered(lambda line: line.hour_type == "pp")[:1]

        self.assertFalse(row_pp.month_01_editable)
        self.assertFalse(row_pp.month_11_editable)
        self.assertTrue(row_pp.month_12_editable)

        with self.assertRaises(ValidationError):
            row_pp.write({"month_01": 8.0})

        row_pp.write({"month_12": 8.0})
        december = self.env["tenenet.project.timesheet"].search([
            ("assignment_id", "=", assignment.id),
            ("period", "=", "2025-12-01"),
        ], limit=1)
        self.assertAlmostEqual(december.hours_pp, 8.0)

    def test_utilization_aggregate_from_timesheets(self):
        self.env["tenenet.project.timesheet"].with_context(from_hr_leave_sync=True).create(self._timesheet_vals(
            period="2026-03-01",
            hours_pp=80.0, hours_np=20.0,
            hours_vacation=10.0, hours_sick=5.0, hours_doctor=3.0,
        ))
        self.env["tenenet.project.timesheet"].with_context(from_hr_leave_sync=True).create(self._timesheet_vals(
            assignment=self.assignment2, period="2026-03-01",
            hours_pp=40.0, hours_np=10.0,
            hours_vacation=5.0,
        ))
        util = self.env["tenenet.utilization"].search([
            ("employee_id", "=", self.employee.id),
            ("period", "=", "2026-03-01"),
        ], limit=1)
        if not util:
            util = self.env["tenenet.utilization"].create({
                "employee_id": self.employee.id,
                "period": "2026-03-01",
            })
        util.invalidate_recordset()
        self.assertAlmostEqual(util.hours_pp, 120.0)
        self.assertAlmostEqual(util.hours_np, 30.0)
        self.assertAlmostEqual(util.hours_vacation, 15.0)
        self.assertAlmostEqual(util.hours_sick, 5.0)
        self.assertAlmostEqual(util.hours_doctor, 3.0)
        self.assertAlmostEqual(util.hours_project_total, 150.0)

    def test_manual_leave_rows_are_blocked(self):
        ts = self.env["tenenet.project.timesheet"].create({
            "assignment_id": self.assignment.id,
            "period": "2026-08-01",
        })
        with self.assertRaises(ValidationError):
            ts.write({"hours_vacation": 2.0})

        with self.assertRaises(ValidationError):
            self.env["tenenet.project.timesheet.line"].create({
                "timesheet_id": ts.id,
                "hour_type": "sick",
                "hours": 3.0,
            })

    def test_matrix_leave_rows_are_blocked_for_manual_edit(self):
        matrix = self.env["tenenet.project.timesheet.matrix"].create({
            "assignment_id": self.assignment.id,
            "year": 2026,
        })
        leave_row = matrix.line_ids.filtered(lambda line: line.hour_type == "vacation")[:1]
        with self.assertRaises(ValidationError):
            leave_row.write({"month_01": 5.0})
