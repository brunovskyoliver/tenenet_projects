from datetime import date

from odoo import api, fields, models
from odoo.exceptions import ValidationError


def _month_start(value):
    return date(value.year, value.month, 1)


def _next_month(value):
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


class TenenetProjectAssignment(models.Model):
    _name = "tenenet.project.assignment"
    _description = "Priradenie zamestnanca k projektu"
    _order = "project_id, employee_id"
    _rec_name = "name"

    name = fields.Char(
        string="Názov",
        compute="_compute_name",
        store=True,
    )

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
    )
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
    )
    date_start = fields.Date(string="Začiatok priradenia")
    date_end = fields.Date(string="Koniec priradenia")
    wage_hm = fields.Float(
        string="Hodinová mzda HM (brutto)",
        digits=(10, 4),
        help="Hodinová brutto mzda zamestnanca pre tento projekt",
    )
    wage_ccp = fields.Float(
        string="Hodinová sadzba CCP (celková cena práce)",
        digits=(10, 4),
        help="Celková cena práce za hodinu pre tento projekt",
    )
    active = fields.Boolean(string="Aktívne", default=True)
    timesheet_ids = fields.One2many(
        "tenenet.project.timesheet",
        "assignment_id",
        string="Timesheety",
    )
    matrix_ids = fields.One2many(
        "tenenet.project.timesheet.matrix",
        "assignment_id",
        string="Ročné matice",
    )
    timesheet_count = fields.Integer(
        string="Počet timesheet záznamov",
        compute="_compute_timesheet_count",
    )

    _unique_employee_project = models.Constraint(
        "UNIQUE(employee_id, project_id)",
        "Zamestnanec môže byť priradený k projektu iba raz.",
    )

    @api.depends("timesheet_ids")
    def _compute_timesheet_count(self):
        for rec in self:
            rec.timesheet_count = len(rec.timesheet_ids)

    @api.depends("employee_id.name", "project_id.name")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.employee_id.name or '-'} / {rec.project_id.name or '-'}"

    def _get_expected_periods(self):
        self.ensure_one()
        start = self.date_start or self.project_id.date_start
        end = self.date_end or self.project_id.date_end

        if not start and not end and self.project_id.year:
            start = date(self.project_id.year, 1, 1)
            current_date = fields.Date.today()
            end = date(
                self.project_id.year,
                min(current_date.month, 12) if self.project_id.year == current_date.year else 12,
                1,
            )

        if not start and not end:
            return []

        if start and not end:
            today = fields.Date.today()
            end = date(today.year, today.month, 1)
        elif end and not start:
            start = date(end.year, 1, 1)

        start = _month_start(start)
        end = _month_start(end)
        if start > end:
            start, end = end, start

        periods = []
        current = start
        while current <= end:
            periods.append(current)
            current = _next_month(current)
        return periods

    def _default_matrix_year(self):
        self.ensure_one()
        periods = self._get_expected_periods()
        if not periods:
            return fields.Date.today().year

        years = {period.year for period in periods}
        current_year = fields.Date.today().year
        if current_year in years:
            return current_year
        return min(years)

    def _get_expected_years(self):
        self.ensure_one()
        return sorted({period.year for period in self._get_expected_periods()})

    def _is_period_in_scope(self, period):
        self.ensure_one()
        periods = self._get_expected_periods()
        if not periods:
            return True
        return _month_start(period) in set(periods)

    def _sync_precreated_timesheets(self):
        Timesheet = self.env["tenenet.project.timesheet"]
        Matrix = self.env["tenenet.project.timesheet.matrix"]

        for rec in self.filtered(lambda assignment: assignment.employee_id and assignment.project_id):
            periods = rec._get_expected_periods()
            existing_periods = set(rec.timesheet_ids.mapped("period"))
            for period in periods:
                if period not in existing_periods:
                    Timesheet.create({
                        "assignment_id": rec.id,
                        "period": period,
                    })

            years = sorted({period.year for period in periods})
            if years:
                Matrix._ensure_for_assignment_years(rec, years)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_precreated_timesheets()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {"employee_id", "project_id", "date_start", "date_end", "active"} & set(vals):
            self._sync_precreated_timesheets()
        return result

    def action_open_timesheet_matrix_current_year(self):
        self.ensure_one()
        year = self._default_matrix_year()
        years = self._get_expected_years() or [year]
        matrix = self.env["tenenet.project.timesheet.matrix"]._ensure_for_assignment_years(
            self,
            years,
        )
        return matrix.filtered(lambda rec: rec.year == year)[:1].action_open_form()

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_start > rec.date_end:
                raise ValidationError(
                    "Dátum začiatku priradenia nemôže byť po dátume konca."
                )
