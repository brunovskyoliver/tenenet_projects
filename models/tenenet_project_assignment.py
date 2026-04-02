import logging
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


def _month_start(value):
    return date(value.year, value.month, 1)


def _next_month(value):
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _ranges_overlap(start_a, end_a, start_b, end_b):
    if start_a and end_b and start_a > end_b:
        return False
    if start_b and end_a and start_b > end_a:
        return False
    return True


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
    site_ids = fields.Many2many(
        "tenenet.project.site",
        "tenenet_project_assignment_site_rel",
        "assignment_id",
        "site_id",
        string="Prevádzky / centrá / terén",
    )
    date_start = fields.Date(string="Začiatok priradenia")
    date_end = fields.Date(string="Koniec priradenia")
    allocation_ratio = fields.Float(
        string="Úväzok na projekte (%)",
        digits=(5, 2),
        default=100.0,
        help="Percento úväzku zamestnanca vyhradené pre tento projekt.",
    )
    settlement_only = fields.Boolean(
        string="Iba na zúčtovanie",
        default=False,
        help="Priradenie slúži iba na zúčtovanie alebo financovanie z iných zdrojov.",
    )
    effective_work_ratio = fields.Float(
        string="Skutočný úväzok (%)",
        digits=(5, 2),
        compute="_compute_effective_work_ratio",
        help="Skutočný úväzok na projekte po zohľadnení celkového úväzku zamestnanca.",
    )
    wage_hm = fields.Float(
        string="Hodinová mzda HM (brutto)",
        digits=(10, 4),
        help="Hodinová brutto mzda zamestnanca pre tento projekt",
    )
    wage_ccp = fields.Float(
        string="Hodinová sadzba CCP (celková cena práce)",
        digits=(10, 4),
        compute="_compute_ccp_fields",
        store=True,
        help="Celková cena práce za hodinu = mzda HM × 1.362",
    )
    max_monthly_wage_hm = fields.Float(
        string="Max. mesačná mzda HM",
        digits=(10, 4),
        default=0.0,
        help="Mesačný strop hrubej mzdy pre toto priradenie. 0 = bez stropu. Predvyplnené z projektu.",
    )
    max_monthly_wage_ccp = fields.Float(
        string="Max. mesačná sadzba CCP",
        digits=(10, 4),
        compute="_compute_ccp_fields",
        store=True,
        help="Mesačný strop CCP = max. mzda HM × 1.362",
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
    state = fields.Selection(
        [
            ("planned", "Budúce"),
            ("active", "Aktívne"),
            ("finished", "Ukončené"),
        ],
        string="Stav",
        compute="_compute_state",
        store=True,
    )
    is_current = fields.Boolean(
        string="Aktuálne",
        compute="_compute_state",
        store=True,
    )

    CCP_MULTIPLIER = 1.362

    @api.depends("employee_id.work_ratio", "allocation_ratio")
    def _compute_effective_work_ratio(self):
        for rec in self:
            rec.effective_work_ratio = rec.allocation_ratio or 0.0

    @api.depends("wage_hm", "max_monthly_wage_hm")
    def _compute_ccp_fields(self):
        for rec in self:
            rec.wage_ccp = (rec.wage_hm or 0.0) * self.CCP_MULTIPLIER
            rec.max_monthly_wage_ccp = (rec.max_monthly_wage_hm or 0.0) * self.CCP_MULTIPLIER

    @api.depends("timesheet_ids")
    def _compute_timesheet_count(self):
        for rec in self:
            rec.timesheet_count = len(rec.timesheet_ids)

    @api.depends("employee_id.name", "project_id.name", "allocation_ratio")
    def _compute_name(self):
        for rec in self:
            ratio = f"{rec.allocation_ratio:.0f} %" if rec.allocation_ratio else "0 %"
            rec.name = f"{rec.employee_id.name or '-'} / {rec.project_id.name or '-'} / {ratio}"

    @api.depends(
        "active",
        "date_start",
        "date_end",
        "project_id.date_start",
        "project_id.date_end",
    )
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for rec in self:
            start, end = rec._get_effective_date_range()
            if not rec.active:
                rec.state = "finished"
                rec.is_current = False
            elif start and start > today:
                rec.state = "planned"
                rec.is_current = False
            elif end and end < today:
                rec.state = "finished"
                rec.is_current = False
            else:
                rec.state = "active"
                rec.is_current = True

    def _get_expected_periods(self):
        self.ensure_one()
        start = self.date_start or self.project_id.date_start
        end = self.date_end or self.project_id.date_end

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

    @api.model
    def _default_rates_for_employee(self, employee):
        assignments = self.search([
            ("employee_id", "=", employee.id),
            ("active", "=", True),
            ("project_id.is_tenenet_internal", "=", False),
        ])
        if assignments:
            count = len(assignments)
            avg_hm = sum(assignments.mapped("wage_hm")) / count
            avg_ccp = sum(assignments.mapped("wage_ccp")) / count
            return avg_hm, avg_ccp
        hourly = employee.hourly_rate or 0.0
        return hourly, hourly

    @api.model
    def _get_or_create_internal_assignment(self, employee):
        _logger.warning(
            "DEPRECATED: _get_or_create_internal_assignment is deprecated. "
            "Use tenenet.internal.expense instead of the internal project mechanism."
        )
        internal_project = self.env["tenenet.project"]._get_or_create_internal_project()
        assignment = self.with_context(active_test=False).search([
            ("employee_id", "=", employee.id),
            ("project_id", "=", internal_project.id),
        ], limit=1)
        if assignment:
            if not assignment.active:
                assignment.active = True
            return assignment

        wage_hm, _wage_ccp = self._default_rates_for_employee(employee)
        return self.create({
            "employee_id": employee.id,
            "project_id": internal_project.id,
            "wage_hm": wage_hm,
            "active": True,
        })

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "project_id" in vals:
                project = self.env["tenenet.project"].browse(vals["project_id"])
                if "max_monthly_wage_hm" not in vals:
                    vals["max_monthly_wage_hm"] = project.default_max_monthly_wage_hm or 0.0
        records = super().create(vals_list)
        records._sync_precreated_timesheets()
        return records

    def unlink(self):
        # Collect affected (employee_id, period) pairs before cascade-deletes them.
        # After deletion the timesheets are gone, so we need to recompute utilization
        # to clear any stale leave/project hours that were stored there.
        affected = {
            (ts.employee_id.id, ts.period)
            for rec in self
            for ts in rec.timesheet_ids
            if ts.employee_id and ts.period
        }
        result = super().unlink()
        if affected:
            Util = self.env["tenenet.utilization"].sudo()
            for emp_id, period in affected:
                util = Util.search([("employee_id", "=", emp_id), ("period", "=", period)])
                if util:
                    util._compute_from_timesheets()
        return result

    def write(self, vals):
        result = super().write(vals)
        timesheets = self.mapped("timesheet_ids")
        if {
            "employee_id",
            "project_id",
            "date_start",
            "date_end",
            "active",
            "allocation_ratio",
        } & set(vals):
            self._sync_precreated_timesheets()
            timesheets = self.mapped("timesheet_ids")
        if {"wage_hm", "max_monthly_wage_hm", "project_id"} & set(vals):
            timesheets._sync_employee_period_costs()
            timesheets._check_wage_cap()
        return result

    def action_open_timesheet_matrix_current_year(self):
        self.ensure_one()
        year = self._default_matrix_year()
        years = self._get_expected_years() or [year]
        matrix = self.env["tenenet.project.timesheet.matrix"]._ensure_for_assignment_years(
            self,
            years,
        )
        return matrix.filtered(lambda rec: rec.year == year)[:1].action_open_grid()

    def action_open_remove_wizard(self):
        self.ensure_one()
        return {
            "name": "Odstrániť priradenie",
            "type": "ir.actions.act_window",
            "res_model": "tenenet.project.assignment.remove.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_assignment_id": self.id},
        }

    def _get_effective_date_range(self):
        self.ensure_one()
        return (
            self.date_start or self.project_id.date_start,
            self.date_end or self.project_id.date_end,
        )

    @api.constrains(
        "active",
        "employee_id",
        "project_id",
        "date_start",
        "date_end",
        "allocation_ratio",
        "site_ids",
    )
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_start > rec.date_end:
                raise ValidationError(
                    "Dátum začiatku priradenia nemôže byť po dátume konca."
                )
            if rec.allocation_ratio <= 0.0 or rec.allocation_ratio > 100.0:
                raise ValidationError("Úväzok na projekte musí byť v rozsahu 0 až 100 %.")
            if not rec.active or not rec.employee_id:
                continue

            start, end = rec._get_effective_date_range()
            overlapping_assignments = self.with_context(active_test=False).search([
                ("id", "!=", rec.id),
                ("employee_id", "=", rec.employee_id.id),
                ("active", "=", True),
            ])
            overlapping_ratio = sum(
                assignment.allocation_ratio
                for assignment in overlapping_assignments
                if _ranges_overlap(start, end, *assignment._get_effective_date_range())
            )
            total_ratio = overlapping_ratio + (rec.allocation_ratio or 0.0)
            max_ratio = rec.employee_id.work_ratio or 0.0
            if total_ratio > max_ratio:
                raise ValidationError(
                    "Súčet projektových úväzkov nesmie prekročiť úväzok zamestnanca (%s %%)."
                    % (f"{max_ratio:.2f}")
                )
            invalid_sites = rec.site_ids - rec.project_id.site_ids
            if invalid_sites:
                raise ValidationError(
                    "Priradenie môže obsahovať iba prevádzky, centrá alebo terén pripojené k projektu."
                )
