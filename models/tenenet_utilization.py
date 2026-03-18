from datetime import date

from odoo import api, fields, models


def _month_start(value):
    return date(value.year, value.month, 1)


def _next_month(value):
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


class TenenetUtilization(models.Model):
    _name = "tenenet.utilization"
    _description = "Vyťaženosť zamestnanca"
    _order = "period desc, employee_id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
    )
    manager_id = fields.Many2one(
        "hr.employee",
        string="Manažér",
        related="employee_id.parent_id",
        store=True,
        readonly=True,
        ondelete="set null",
    )
    manager_name = fields.Char(
        string="Manažér",
        related="manager_id.name",
        store=True,
        readonly=True,
        translate=False,
    )
    period = fields.Date(string="Obdobie", required=True)

    work_ratio = fields.Float(
        string="Úväzok (%)",
        digits=(5, 2),
        related="employee_id.work_ratio",
        store=True,
        readonly=True,
    )
    capacity_hours = fields.Float(
        string="Pracovné hodiny (mesiac)",
        digits=(10, 2),
        related="employee_id.work_hours",
        store=True,
        readonly=True,
    )

    # Projektové hodiny – vypočítané z timesheet záznamov.
    hours_pp = fields.Float(string="Hodiny PP", digits=(10, 2), compute="_compute_from_timesheets", store=True)
    hours_np = fields.Float(string="Hodiny NP", digits=(10, 2), compute="_compute_from_timesheets", store=True)
    hours_travel = fields.Float(
        string="Hodiny cesta za klientom",
        digits=(10, 2),
        compute="_compute_from_timesheets",
        store=True,
    )
    hours_training = fields.Float(
        string="Hodiny školenie",
        digits=(10, 2),
        compute="_compute_from_timesheets",
        store=True,
    )
    hours_ambulance = fields.Float(
        string="Hodiny ambulancia",
        digits=(10, 2),
        compute="_compute_from_timesheets",
        store=True,
    )
    hours_international = fields.Float(
        string="Hodiny medzinárodné projekty",
        digits=(10, 2),
        compute="_compute_from_timesheets",
        store=True,
    )
    hours_project_total = fields.Float(
        string="Projektové hodiny spolu",
        digits=(10, 2),
        compute="_compute_hours_project_total",
        store=True,
    )

    # Absencie – vypočítané z timesheet záznamov.
    hours_vacation = fields.Float(string="Hodiny dovolenka", digits=(10, 2), compute="_compute_from_timesheets", store=True)
    hours_doctor = fields.Float(string="Hodiny lekár", digits=(10, 2), compute="_compute_from_timesheets", store=True)
    hours_sick = fields.Float(string="Hodiny PN/OČR", digits=(10, 2), compute="_compute_from_timesheets", store=True)
    hours_holidays = fields.Float(
        string="Hodiny sviatky",
        digits=(10, 2),
        compute="_compute_from_timesheets",
        store=True,
    )
    leaves_kpi_hours = fields.Float(
        string="Absencie pre KPI",
        digits=(10, 2),
        compute="_compute_leaves_kpi_hours",
        store=True,
        help="Dovolenka + lekár + PN/OČR.",
    )
    hours_ballast = fields.Float(
        string="Hodiny balast",
        digits=(10, 2),
        compute="_compute_hours_ballast",
        store=True,
        help="NP + cesta + školenie + dovolenka + lekár + PN/OČR.",
    )
    hours_non_project_total = fields.Float(
        string="Balast spolu",
        digits=(10, 2),
        compute="_compute_hours_non_project_total",
        store=True,
    )

    utilization_rate = fields.Float(
        string="Miera vyťaženosti (PP)",
        digits=(6, 4),
        compute="_compute_utilization_rate",
        store=True,
    )
    utilization_percentage = fields.Float(
        string="Procento vyťaženosti (PP)",
        digits=(5, 2),
        compute="_compute_utilization_percentage",
    )
    utilization_status = fields.Selection(
        [("ok", "OK"), ("warning", "!")],
        string="Stav vyťaženosti",
        compute="_compute_utilization_status",
        store=True,
    )
    non_project_rate = fields.Float(
        string="Miera balastu",
        digits=(6, 4),
        compute="_compute_non_project_rate",
        store=True,
    )
    non_project_percentage = fields.Float(
        string="Procento balastu",
        digits=(5, 2),
        compute="_compute_non_project_percentage",
    )
    non_project_status = fields.Selection(
        [("ok", "OK"), ("warning", "!")],
        string="Stav balastu",
        compute="_compute_non_project_status",
        store=True,
    )
    hours_diff = fields.Float(
        string="Rozdiel hodín",
        digits=(10, 2),
        compute="_compute_hours_diff",
        store=True,
    )

    _unique_employee_period = models.Constraint(
        "UNIQUE(employee_id, period)",
        "Pre zamestnanca môže existovať len jeden záznam vyťaženosti za obdobie.",
    )

    @api.model
    def _normalize_period(self, period):
        return _month_start(fields.Date.to_date(period))

    @api.model
    def _current_period(self):
        return _month_start(fields.Date.today())

    @api.depends('non_project_rate')
    def _compute_non_project_percentage(self):
        for rec in self:
            rec.non_project_percentage = (rec.non_project_rate * 100) if rec.capacity_hours > 0 else 0.0

    @api.depends('utilization_rate')
    def _compute_utilization_percentage(self):
        for rec in self:
            rec.utilization_percentage = (rec.utilization_rate * 100) if rec.capacity_hours > 0 else 0.0

    @api.model
    def _sync_for_period(self, period, employee_ids=None):
        normalized_period = self._normalize_period(period)
        employee_domain = [("active", "=", True)]
        if employee_ids:
            employee_domain.append(("id", "in", list(set(employee_ids))))
        employees = self.env["hr.employee"].search(employee_domain)
        if not employees:
            return self.browse()

        existing = self.search([
            ("period", "=", normalized_period),
            ("employee_id", "in", employees.ids),
        ])
        existing_by_employee = {rec.employee_id.id: rec for rec in existing}
        create_vals = [
            {"employee_id": employee.id, "period": normalized_period}
            for employee in employees
            if employee.id not in existing_by_employee
        ]
        if create_vals:
            self.create(create_vals)

        return self.search([
            ("period", "=", normalized_period),
            ("employee_id", "in", employees.ids),
        ])

    @api.model
    def _sync_for_period_range(self, date_from, date_to, employee_ids=None):
        start = self._normalize_period(date_from)
        end = self._normalize_period(date_to)
        if start > end:
            start, end = end, start

        current = start
        records = self.browse()
        while current <= end:
            records |= self._sync_for_period(current, employee_ids=employee_ids)
            current = _next_month(current)
        return records

    @api.model
    def _sync_current_period(self):
        return self._sync_for_period(self._current_period())

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("period"):
                vals["period"] = self._normalize_period(vals["period"])
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("period"):
            vals["period"] = self._normalize_period(vals["period"])
        return super().write(vals)

    @api.depends(
        "employee_id",
        "period",
        "employee_id.assignment_ids.timesheet_ids.period",
        "employee_id.assignment_ids.timesheet_ids.hours_pp",
        "employee_id.assignment_ids.timesheet_ids.hours_np",
        "employee_id.assignment_ids.timesheet_ids.hours_travel",
        "employee_id.assignment_ids.timesheet_ids.hours_training",
        "employee_id.assignment_ids.timesheet_ids.hours_ambulance",
        "employee_id.assignment_ids.timesheet_ids.hours_international",
        "employee_id.assignment_ids.timesheet_ids.hours_vacation",
        "employee_id.assignment_ids.timesheet_ids.hours_doctor",
        "employee_id.assignment_ids.timesheet_ids.hours_sick",
        "employee_id.assignment_ids.timesheet_ids.hours_holidays",
    )
    def _compute_from_timesheets(self):
        Timesheet = self.env["tenenet.project.timesheet"]
        zero_fields = (
            "hours_pp",
            "hours_np",
            "hours_travel",
            "hours_training",
            "hours_ambulance",
            "hours_international",
            "hours_vacation",
            "hours_doctor",
            "hours_sick",
            "hours_holidays",
        )
        for rec in self:
            if not rec.employee_id or not rec.period:
                for field_name in zero_fields:
                    rec[field_name] = 0.0
                continue

            lines = Timesheet.search([
                ("employee_id", "=", rec.employee_id.id),
                ("period", "=", rec.period),
            ])
            rec.hours_pp = sum(lines.mapped("hours_pp"))
            rec.hours_np = sum(lines.mapped("hours_np"))
            rec.hours_travel = sum(lines.mapped("hours_travel"))
            rec.hours_training = sum(lines.mapped("hours_training"))
            rec.hours_ambulance = sum(lines.mapped("hours_ambulance"))
            rec.hours_international = sum(lines.mapped("hours_international"))
            rec.hours_vacation = sum(lines.mapped("hours_vacation"))
            rec.hours_doctor = sum(lines.mapped("hours_doctor"))
            rec.hours_sick = sum(lines.mapped("hours_sick"))
            rec.hours_holidays = sum(lines.mapped("hours_holidays"))

    @api.depends(
        "hours_pp",
        "hours_np",
        "hours_travel",
        "hours_training",
        "hours_ambulance",
        "hours_international",
    )
    def _compute_hours_project_total(self):
        for rec in self:
            rec.hours_project_total = (
                (rec.hours_pp or 0.0)
                + (rec.hours_np or 0.0)
                + (rec.hours_travel or 0.0)
                + (rec.hours_training or 0.0)
                + (rec.hours_ambulance or 0.0)
                + (rec.hours_international or 0.0)
            )

    @api.depends("hours_vacation", "hours_doctor", "hours_sick")
    def _compute_leaves_kpi_hours(self):
        for rec in self:
            rec.leaves_kpi_hours = (
                (rec.hours_vacation or 0.0)
                + (rec.hours_doctor or 0.0)
                + (rec.hours_sick or 0.0)
            )

    @api.depends(
        "hours_np",
        "hours_travel",
        "hours_training",
        "hours_vacation",
        "hours_doctor",
        "hours_sick",
    )
    def _compute_hours_ballast(self):
        for rec in self:
            rec.hours_ballast = (
                (rec.hours_np or 0.0)
                + (rec.hours_travel or 0.0)
                + (rec.hours_training or 0.0)
                + (rec.hours_vacation or 0.0)
                + (rec.hours_doctor or 0.0)
                + (rec.hours_sick or 0.0)
            )

    @api.depends("hours_ballast")
    def _compute_hours_non_project_total(self):
        for rec in self:
            rec.hours_non_project_total = rec.hours_ballast or 0.0

    @api.depends("hours_pp", "capacity_hours", "leaves_kpi_hours")
    def _compute_utilization_rate(self):
        for rec in self:
            available_hours = (rec.capacity_hours or 0.0) - (rec.leaves_kpi_hours or 0.0)
            rec.utilization_rate = (rec.hours_pp / available_hours) if available_hours > 0 else 0.0

    @api.depends("utilization_rate", "capacity_hours", "leaves_kpi_hours")
    def _compute_utilization_status(self):
        for rec in self:
            available_hours = (rec.capacity_hours or 0.0) - (rec.leaves_kpi_hours or 0.0)
            rec.utilization_status = "ok" if available_hours > 0 and rec.utilization_rate >= 0.8 else "warning"

    @api.depends("hours_ballast", "capacity_hours")
    def _compute_non_project_rate(self):
        for rec in self:
            rec.non_project_rate = (
                (rec.hours_ballast / rec.capacity_hours) if rec.capacity_hours > 0 else 0.0
            )

    @api.depends("non_project_rate", "capacity_hours")
    def _compute_non_project_status(self):
        for rec in self:
            rec.non_project_status = "ok" if rec.capacity_hours > 0 and rec.non_project_rate <= 0.25 else "warning"

    @api.depends(
        "hours_project_total",
        "hours_vacation",
        "hours_doctor",
        "hours_sick",
        "hours_holidays",
        "capacity_hours",
    )
    def _compute_hours_diff(self):
        for rec in self:
            rec.hours_diff = (
                (rec.hours_project_total or 0.0)
                + (rec.hours_vacation or 0.0)
                + (rec.hours_doctor or 0.0)
                + (rec.hours_sick or 0.0)
                + (rec.hours_holidays or 0.0)
                - (rec.capacity_hours or 0.0)
            )
