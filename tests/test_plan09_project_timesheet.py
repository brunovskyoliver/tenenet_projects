from psycopg2 import IntegrityError

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTenenetPlan09ProjectTimesheet(TransactionCase):
    def setUp(self):
        super().setUp()
        self.employee = self.env["hr.employee"].create({"name": "Zamestnanec Timesheet"})
        self.project = self.env["tenenet.project"].create({"name": "Projekt Timesheet"})
        self.project2 = self.env["tenenet.project"].create({"name": "Projekt Timesheet 2"})
        self.assignment = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.project.id,
            "wage_hm": 10.0,
            "wage_ccp": 13.62,
        })
        self.assignment2 = self.env["tenenet.project.assignment"].create({
            "employee_id": self.employee.id,
            "project_id": self.project2.id,
            "wage_hm": 12.0,
            "wage_ccp": 16.0,
        })

    def _timesheet_vals(self, assignment=None, **overrides):
        vals = {
            "assignment_id": (assignment or self.assignment).id,
            "period": "2026-01-01",
            "hours_pp": 80.0,
            "hours_np": 20.0,
            "hours_vacation": 10.0,
        }
        vals.update(overrides)
        return vals

    def test_computed_hour_totals(self):
        ts = self.env["tenenet.project.timesheet"].create(self._timesheet_vals(
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

    def test_tenenet_cost_residual_computation(self):
        self.env["tenenet.project.timesheet"].create(self._timesheet_vals(
            hours_pp=100.0, hours_np=0.0, hours_vacation=0.0
        ))
        self.env["tenenet.project.timesheet"].create(self._timesheet_vals(
            assignment=self.assignment2, period="2026-01-01",
            hours_pp=50.0, hours_np=0.0, hours_vacation=0.0
        ))
        cost = self.env["tenenet.employee.tenenet.cost"].create({
            "employee_id": self.employee.id,
            "period": "2026-01-01",
            "gross_salary_employee": 2000.0,
            "total_labor_cost_employee": 2724.0,
        })
        cost.invalidate_recordset()
        # project billed: 100 * 10 + 50 * 12 = 1000 + 600 = 1600
        self.assertAlmostEqual(cost.project_billed_gross, 1600.0, places=2)
        self.assertAlmostEqual(cost.tenenet_residual_hm, 400.0, places=2)

    def test_utilization_aggregate_from_timesheets(self):
        self.env["tenenet.project.timesheet"].create(self._timesheet_vals(
            period="2026-03-01",
            hours_pp=80.0, hours_np=20.0,
            hours_vacation=10.0, hours_sick=5.0, hours_doctor=3.0,
        ))
        self.env["tenenet.project.timesheet"].create(self._timesheet_vals(
            assignment=self.assignment2, period="2026-03-01",
            hours_pp=40.0, hours_np=10.0,
            hours_vacation=5.0,
        ))
        util = self.env["tenenet.utilization"].create({
            "employee_id": self.employee.id,
            "period": "2026-03-01",
            "capacity_hours": 176.0,
        })
        util.invalidate_recordset()
        self.assertAlmostEqual(util.hours_pp, 120.0)
        self.assertAlmostEqual(util.hours_np, 30.0)
        self.assertAlmostEqual(util.hours_vacation, 15.0)
        self.assertAlmostEqual(util.hours_sick, 5.0)
        self.assertAlmostEqual(util.hours_doctor, 3.0)
        self.assertAlmostEqual(util.hours_project_total, 150.0)
