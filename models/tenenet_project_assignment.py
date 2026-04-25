import logging
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

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
    program_id = fields.Many2one(
        "tenenet.program",
        string="Program",
        ondelete="restrict",
        help="Program v rámci projektu, pod ktorý spadá toto priradenie.",
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
    ratio_month_ids = fields.One2many(
        "tenenet.project.assignment.ratio.month",
        "assignment_id",
        string="Mesačný alokačný plán",
    )
    has_explicit_ratio_plan = fields.Boolean(
        string="Má mesačný alokačný plán",
        compute="_compute_has_explicit_ratio_plan",
    )
    ratio_planner_state = fields.Json(
        string="Alokačný planner",
        compute="_compute_ratio_planner_state",
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
    tenenet_can_open_employee_card = fields.Boolean(
        string="Môže otvoriť kartu zamestnanca",
        compute="_compute_tenenet_can_open_employee_card",
    )

    CCP_MULTIPLIER = 1.362

    @api.depends("employee_id.work_ratio", "allocation_ratio", "ratio_month_ids.allocation_ratio", "ratio_month_ids.period")
    def _compute_effective_work_ratio(self):
        current_period = fields.Date.context_today(self).replace(day=1)
        for rec in self:
            rec.effective_work_ratio = rec._get_effective_allocation_ratio(current_period) if rec.id else (rec.allocation_ratio or 0.0)

    @api.depends("ratio_month_ids")
    def _compute_has_explicit_ratio_plan(self):
        for rec in self:
            rec.has_explicit_ratio_plan = bool(rec.ratio_month_ids)

    def _compute_ratio_planner_state(self):
        current_year = fields.Date.context_today(self).year
        for rec in self:
            rec.ratio_planner_state = {
                "assignment_id": rec.id or False,
                "current_year": current_year,
            }

    def _get_ccp_multiplier(self):
        self.ensure_one()
        employee = self.employee_id
        if employee and hasattr(employee, "_get_payroll_contribution_multiplier"):
            return employee._get_payroll_contribution_multiplier()
        return self.CCP_MULTIPLIER

    @api.depends("wage_hm", "max_monthly_wage_hm", "employee_id.tenenet_payroll_contribution_multiplier")
    def _compute_ccp_fields(self):
        for rec in self:
            multiplier = rec._get_ccp_multiplier()
            rec.wage_ccp = (rec.wage_hm or 0.0) * multiplier
            rec.max_monthly_wage_ccp = (rec.max_monthly_wage_hm or 0.0) * multiplier

    @api.depends("timesheet_ids")
    def _compute_timesheet_count(self):
        for rec in self:
            rec.timesheet_count = len(rec.timesheet_ids)

    @api.depends("employee_id.name", "project_id.name", "program_id.name", "allocation_ratio", "effective_work_ratio")
    def _compute_name(self):
        for rec in self:
            display_ratio = rec.effective_work_ratio if rec.id else rec.allocation_ratio
            ratio = f"{display_ratio:.0f} %" if display_ratio else "0 %"
            fallback_program = rec.project_id._get_effective_reporting_program()
            program = rec.program_id.display_name or fallback_program.display_name or "-"
            rec.name = f"{rec.employee_id.name or '-'} / {rec.project_id.name or '-'} / {program} / {ratio}"

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

    def _is_active_in_period(self, period):
        self.ensure_one()
        if not self.active:
            return False
        normalized_period = _month_start(fields.Date.to_date(period))
        start, end = self._get_effective_date_range()
        if start and _month_start(start) > normalized_period:
            return False
        if end and _month_start(end) < normalized_period:
            return False
        return True

    def _get_effective_allocation_ratio(self, period):
        self.ensure_one()
        if not period:
            return self.allocation_ratio or 0.0
        normalized_period = _month_start(fields.Date.to_date(period))
        explicit = self.ratio_month_ids.filtered(lambda line: line.period == normalized_period)[:1]
        if explicit:
            return explicit.allocation_ratio or 0.0
        return self.allocation_ratio or 0.0

    def _get_effective_work_ratio_for_period(self, period):
        self.ensure_one()
        return self._get_effective_allocation_ratio(period)

    def _get_fixed_salary_share(self, period):
        self.ensure_one()
        if not self._is_active_in_period(period):
            return 0.0
        target_ccp = self.employee_id._get_effective_monthly_gross_salary_target(period) or 0.0
        if target_ccp <= 0.0:
            return 0.0
        return target_ccp * (self._get_effective_allocation_ratio(period) / 100.0)

    def _get_fixed_salary_share_hm(self, period):
        self.ensure_one()
        if not self._is_active_in_period(period):
            return 0.0
        target_hm = self.employee_id._get_effective_monthly_gross_salary_target_hm(period) or 0.0
        if target_hm <= 0.0:
            return 0.0
        return target_hm * (self._get_effective_allocation_ratio(period) / 100.0)

    def _get_ratio_plan_years(self):
        self.ensure_one()
        years = set(self.ratio_month_ids.mapped("year"))
        years |= set(self._get_expected_years())
        years.add(fields.Date.context_today(self).year)
        return sorted(year for year in years if year)

    def get_ratio_planner_data(self, year=None):
        self.ensure_one()
        selected_year = int(year or fields.Date.context_today(self).year)
        fallback_ratio = self.allocation_ratio or 0.0
        explicit_by_month = {
            line.month: line.allocation_ratio or 0.0
            for line in self.ratio_month_ids.filtered(lambda item: item.year == selected_year)
        }
        months = {}
        explicit_months = []
        for month in range(1, 13):
            is_explicit = month in explicit_by_month
            months[str(month)] = explicit_by_month[month] if is_explicit else fallback_ratio
            if is_explicit:
                explicit_months.append(month)
        return {
            "assignment_id": self.id,
            "project_id": self.project_id.id,
            "employee_id": self.employee_id.id,
            "year": selected_year,
            "available_years": self._get_ratio_plan_years(),
            "label": self.display_name,
            "project_name": self.project_id.display_name or "",
            "employee_name": self.employee_id.display_name or "",
            "fallback_ratio": fallback_ratio,
            "months": months,
            "explicit_months": explicit_months,
        }

    def set_month_ratios(self, year, month_ratios):
        self.ensure_one()
        if not isinstance(month_ratios, dict):
            raise ValidationError("Mesačný alokačný plán musí byť zadaný ako mapa mesiacov.")
        selected_year = int(year or fields.Date.context_today(self).year)
        RatioMonth = self.env["tenenet.project.assignment.ratio.month"]
        touched_periods = set()
        for month_key, ratio in month_ratios.items():
            month = int(month_key)
            if month < 1 or month > 12:
                raise ValidationError("Mesiace alokačného plánu musia byť v rozsahu 1 až 12.")
            ratio_value = round(float(ratio or 0.0), 2)
            if ratio_value < 0.0 or ratio_value > 100.0:
                raise ValidationError("Mesačný úväzok musí byť v rozsahu 0 až 100 %.")
            period = date(selected_year, month, 1)
            touched_periods.add(period)
            existing = self.ratio_month_ids.filtered(lambda line: line.period == period)[:1]
            if existing:
                existing.allocation_ratio = ratio_value
            else:
                RatioMonth.create({
                    "assignment_id": self.id,
                    "period": period,
                    "allocation_ratio": ratio_value,
                })
        self._after_ratio_plan_changed(touched_periods)
        return True

    def clear_month_ratios(self, year, months):
        self.ensure_one()
        selected_year = int(year or fields.Date.context_today(self).year)
        normalized_months = {int(month) for month in months}
        periods = {date(selected_year, month, 1) for month in normalized_months}
        self.ratio_month_ids.filtered(lambda line: line.period in periods).unlink()
        self._after_ratio_plan_changed(periods)
        return True

    def action_open_ratio_planner(self):
        self.ensure_one()
        return {
            "name": "Alokačný plán",
            "type": "ir.actions.client",
            "tag": "tenenet_assignment_ratio_planner_action",
            "target": "new",
            "params": {
                "assignment_id": self.id,
                "year": fields.Date.context_today(self).year,
            },
            "context": dict(self.env.context, dialog_size="extra-large"),
        }

    def _after_ratio_plan_changed(self, periods=None):
        if not self:
            return
        periods = {fields.Date.to_date(period).replace(day=1) for period in (periods or []) if period}
        self._check_capacity_for_periods(periods)
        Cost = self.env["tenenet.employee.tenenet.cost"].sudo()
        Cost._sync_for_assignments_periods(self, periods=periods or None)

    def _get_hours_salary_share(self, period):
        self.ensure_one()
        normalized_period = _month_start(fields.Date.to_date(period))
        timesheets = self.timesheet_ids.filtered(lambda timesheet: timesheet.period == normalized_period)
        gross_salary = sum(timesheets.mapped("gross_salary"))
        total_labor_cost = sum(timesheets.mapped("total_labor_cost"))
        has_labor_cost_override = any(timesheets.mapped("labor_cost_override"))
        wage_internal = self.env["tenenet.internal.expense"].sudo().search([
            ("source_assignment_id", "=", self.id),
            ("period", "=", normalized_period),
            ("category", "=", "wage"),
        ], limit=1)
        if wage_internal:
            gross_salary = max(0.0, gross_salary - (wage_internal.cost_hm or 0.0))
            total_labor_cost = max(0.0, total_labor_cost - (wage_internal.cost_ccp or 0.0))
        return {
            "hm": gross_salary,
            "ccp": total_labor_cost,
            "has_labor_cost_override": has_labor_cost_override,
        }

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
        hourly_ccp = employee.hourly_rate or 0.0
        multiplier = employee._get_payroll_contribution_multiplier() if hasattr(employee, "_get_payroll_contribution_multiplier") else self.CCP_MULTIPLIER
        return hourly_ccp / multiplier if hourly_ccp else 0.0, hourly_ccp

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
                if "program_id" not in vals:
                    vals["program_id"] = (
                        project._get_effective_reporting_program().id
                        or project.program_ids.filtered(lambda rec: rec.code != "ADMIN_TENENET")[:1].id
                        or project.program_ids[:1].id
                    )
        records = super().create(vals_list)
        records._sync_precreated_timesheets()
        self.env["tenenet.employee.tenenet.cost"].sudo()._sync_for_assignments_periods(records)
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
        cost_recompute_keys = {
            (rec.employee_id.id, period)
            for rec in self
            if rec.employee_id
            for period in set(rec._get_expected_periods()) | set(rec.timesheet_ids.mapped("period"))
        }
        result = super().unlink()
        if affected:
            Util = self.env["tenenet.utilization"].sudo()
            for emp_id, period in affected:
                util = Util.search([("employee_id", "=", emp_id), ("period", "=", period)])
                if util:
                    util._compute_from_timesheets()
        if cost_recompute_keys:
            Cost = self.env["tenenet.employee.tenenet.cost"].sudo()
            for emp_id, period in cost_recompute_keys:
                Cost._sync_for_employee_period(emp_id, period)
        return result

    def write(self, vals):
        previous_cost_keys = {
            (rec.employee_id.id, period)
            for rec in self
            if rec.employee_id
            for period in set(rec._get_expected_periods()) | set(rec.timesheet_ids.mapped("period"))
        }
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
            self.env["tenenet.employee.tenenet.cost"].sudo()._sync_for_assignments_periods(self)
            if previous_cost_keys:
                Cost = self.env["tenenet.employee.tenenet.cost"].sudo()
                for employee_id, period in previous_cost_keys:
                    Cost._sync_for_employee_period(employee_id, period)
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

    @api.depends("is_current", "project_id.active", "project_id.project_manager_id.user_id")
    @api.depends_context("uid")
    def _compute_tenenet_can_open_employee_card(self):
        current_user = self.env.user
        for assignment in self:
            assignment.tenenet_can_open_employee_card = bool(
                assignment.is_current
                and assignment.project_id.active
                and assignment.project_id.project_manager_id.user_id == current_user
            )

    def action_open_employee_card_readonly(self):
        self.ensure_one()
        if not self.tenenet_can_open_employee_card:
            raise UserError(
                _("Kartu zamestnanca môže otvoriť iba projektový manažér aktuálneho priradenia.")
            )
        private_form = self.env.ref("hr.view_employee_form", raise_if_not_found=False)
        action = {
            "type": "ir.actions.act_window",
            "name": _("Karta zamestnanca"),
            "res_model": "hr.employee",
            "res_id": self.employee_id.id,
            "view_mode": "form",
            "views": [(private_form.id, "form")] if private_form else [(False, "form")],
            "target": "current",
            "context": {
                "active_id": self.employee_id.id,
                "active_ids": [self.employee_id.id],
                "active_model": "hr.employee",
                "tenenet_private_card_access_employee_ids": [self.employee_id.id],
                "chat_icon": True,
                "form_view_initial_mode": "readonly",
            },
        }
        if private_form:
            action["view_id"] = private_form.id
        return action

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

    def _get_capacity_check_periods(self, assignments):
        periods = {fields.Date.context_today(self).replace(day=1)}
        for assignment in assignments:
            periods.update(assignment.ratio_month_ids.mapped("period"))
            expected = assignment._get_expected_periods()
            if expected:
                periods.update(expected)
        return {period for period in periods if period}

    def _check_capacity_for_periods(self, extra_periods=None):
        if self.env.context.get("skip_tenenet_assignment_capacity_check"):
            return
        extra_periods = {fields.Date.to_date(period).replace(day=1) for period in (extra_periods or []) if period}
        for rec in self:
            if not rec.active or not rec.employee_id:
                continue
            start, end = rec._get_effective_date_range()
            overlapping_assignments = self.with_context(active_test=False).search([
                ("employee_id", "=", rec.employee_id.id),
                ("active", "=", True),
            ])
            overlapping_assignments = overlapping_assignments.filtered(
                lambda assignment: _ranges_overlap(start, end, *assignment._get_effective_date_range())
            )
            periods = rec._get_capacity_check_periods(overlapping_assignments) | extra_periods
            max_ratio = rec.employee_id.work_ratio or 0.0
            for period in periods:
                active_assignments = overlapping_assignments.filtered(lambda assignment: assignment._is_active_in_period(period))
                total_ratio = sum(
                    assignment._get_effective_allocation_ratio(period)
                    for assignment in active_assignments
                )
                if total_ratio > max_ratio:
                    raise ValidationError(
                        "Súčet projektových úväzkov v mesiaci %s nesmie prekročiť úväzok zamestnanca (%s %%)."
                        % (period.strftime("%m/%Y"), f"{max_ratio:.2f}")
                    )

    @api.constrains(
        "active",
        "employee_id",
        "project_id",
        "date_start",
        "date_end",
        "allocation_ratio",
        "program_id",
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
            if self.env.context.get("skip_tenenet_assignment_capacity_check"):
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
            rec._check_capacity_for_periods()
            invalid_sites = rec.site_ids - rec.project_id.site_ids
            if invalid_sites:
                raise ValidationError(
                    "Priradenie môže obsahovať iba prevádzky, centrá alebo terén pripojené k projektu."
                )
            if rec.program_id and rec.program_id not in rec.project_id.program_ids:
                raise ValidationError("Program priradenia musí patriť medzi programy projektu.")
