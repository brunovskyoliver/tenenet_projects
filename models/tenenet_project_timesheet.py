import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

HOUR_FIELD_META = {
    "hours_pp": {
        "type": "pp",
        "label": "PP",
        "scope": "project",
        "sequence": 10,
        "full_label": "Hodiny PP (priama práca)",
    },
    "hours_np": {
        "type": "np",
        "label": "NP",
        "scope": "project",
        "sequence": 20,
        "full_label": "Hodiny NP (nepriama práca)",
    },
    "hours_travel": {
        "type": "travel",
        "label": "Cesta",
        "scope": "project",
        "sequence": 30,
        "full_label": "Hodiny cesta za klientom",
    },
    "hours_training": {
        "type": "training",
        "label": "Školenie",
        "scope": "project",
        "sequence": 40,
        "full_label": "Hodiny školenie",
    },
    "hours_ambulance": {
        "type": "ambulance",
        "label": "Ambulancia",
        "scope": "project",
        "sequence": 50,
        "full_label": "Hodiny ambulancia",
    },
    "hours_international": {
        "type": "international",
        "label": "Medzinárodné",
        "scope": "project",
        "sequence": 60,
        "full_label": "Hodiny medzinárodné projekty",
    },
    "hours_vacation": {
        "type": "vacation",
        "label": "Dovolenka",
        "scope": "leave",
        "sequence": 70,
        "full_label": "Hodiny dovolenka",
    },
    "hours_sick": {
        "type": "sick",
        "label": "PN/OČR",
        "scope": "leave",
        "sequence": 80,
        "full_label": "Hodiny PN/OČR",
    },
    "hours_doctor": {
        "type": "doctor",
        "label": "Lekár",
        "scope": "leave",
        "sequence": 90,
        "full_label": "Hodiny lekár",
    },
    "hours_holidays": {
        "type": "holidays",
        "label": "Sviatky",
        "scope": "leave",
        "sequence": 100,
        "full_label": "Hodiny platené sviatky",
    },
}

HOUR_TYPE_SELECTION = [(meta["type"], meta["label"]) for meta in HOUR_FIELD_META.values()]
HOUR_SCOPE_SELECTION = [
    ("project", "Projektové hodiny"),
    ("leave", "Absencie"),
]
HOUR_FIELD_BY_TYPE = {
    meta["type"]: field_name for field_name, meta in HOUR_FIELD_META.items()
}
LEAVE_HOUR_TYPES = tuple(
    meta["type"] for meta in HOUR_FIELD_META.values() if meta["scope"] == "leave"
)


class TenenetProjectTimesheet(models.Model):
    _name = "tenenet.project.timesheet"
    _description = "Mesačný timesheet zamestnanca na projekte"
    _order = "period desc, project_id, employee_id"

    assignment_id = fields.Many2one(
        "tenenet.project.assignment",
        string="Priradenie",
        required=True,
        ondelete="cascade",
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        related="assignment_id.employee_id",
        store=True,
        readonly=True,
    )
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        related="assignment_id.project_id",
        store=True,
        readonly=True,
    )
    period = fields.Date(
        string="Obdobie",
        required=True,
        help="Prvý deň mesiaca",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
    )
    line_ids = fields.One2many(
        "tenenet.project.timesheet.line",
        "timesheet_id",
        string="Riadky hodín",
    )

    # ── Projektové hodiny / absencie agregované z riadkov ───────────────────
    hours_pp = fields.Float(string="Hodiny PP (priama práca)", digits=(10, 2), compute="_compute_hours_from_lines", inverse="_inverse_hours_from_parent", store=True)
    hours_np = fields.Float(string="Hodiny NP (nepriama práca)", digits=(10, 2), compute="_compute_hours_from_lines", inverse="_inverse_hours_from_parent", store=True)
    hours_travel = fields.Float(string="Hodiny cesta za klientom", digits=(10, 2), compute="_compute_hours_from_lines", inverse="_inverse_hours_from_parent", store=True)
    hours_training = fields.Float(string="Hodiny školenie", digits=(10, 2), compute="_compute_hours_from_lines", inverse="_inverse_hours_from_parent", store=True)
    hours_ambulance = fields.Float(string="Hodiny ambulancia", digits=(10, 2), compute="_compute_hours_from_lines", inverse="_inverse_hours_from_parent", store=True)
    hours_international = fields.Float(string="Hodiny medzinárodné projekty", digits=(10, 2), compute="_compute_hours_from_lines", inverse="_inverse_hours_from_parent", store=True)
    hours_project_total = fields.Float(
        string="Projektové hodiny spolu",
        digits=(10, 2),
        compute="_compute_hours_from_lines",
        store=True,
    )
    hours_vacation = fields.Float(string="Hodiny dovolenka", digits=(10, 2), compute="_compute_hours_from_lines", inverse="_inverse_hours_from_parent", store=True)
    hours_sick = fields.Float(string="Hodiny PN/OČR", digits=(10, 2), compute="_compute_hours_from_lines", inverse="_inverse_hours_from_parent", store=True)
    hours_doctor = fields.Float(string="Hodiny lekár", digits=(10, 2), compute="_compute_hours_from_lines", inverse="_inverse_hours_from_parent", store=True)
    hours_holidays = fields.Float(string="Hodiny platené sviatky", digits=(10, 2), compute="_compute_hours_from_lines", inverse="_inverse_hours_from_parent", store=True)
    hours_leave_total = fields.Float(
        string="Absencie spolu",
        digits=(10, 2),
        compute="_compute_hours_from_lines",
        store=True,
    )
    leave_auto_synced = fields.Boolean(
        string="Absencie sync. z hr_holidays",
        default=False,
        help="Označuje, že hodiny absencií boli automaticky synchronizované z Odoo dovoleniek.",
    )
    hours_total = fields.Float(
        string="Hodiny spolu",
        digits=(10, 2),
        compute="_compute_hours_from_lines",
        store=True,
    )

    # ── Mzda / náklady ───────────────────────────────────────────────────────
    wage_hm = fields.Float(
        string="Hodinová mzda HM",
        related="assignment_id.wage_hm",
        store=True,
        readonly=True,
        digits=(10, 4),
    )
    wage_ccp = fields.Float(
        string="Hodinová sadzba CCP",
        related="assignment_id.wage_ccp",
        store=True,
        readonly=True,
        digits=(10, 4),
    )
    gross_salary = fields.Monetary(
        string="Hrubá mzda",
        currency_field="currency_id",
        compute="_compute_costs",
        store=True,
    )
    deductions = fields.Monetary(
        string="Odvody",
        currency_field="currency_id",
        compute="_compute_costs",
        store=True,
    )
    total_labor_cost = fields.Monetary(
        string="Celková cena práce",
        currency_field="currency_id",
        compute="_compute_costs",
        store=True,
    )

    _unique_assignment_period = models.Constraint(
        "UNIQUE(assignment_id, period)",
        "Pre priradenie môže existovať len jeden timesheet záznam za obdobie.",
    )

    @api.model
    def _hour_field_names(self):
        return tuple(HOUR_FIELD_META.keys())

    @api.model
    def _normalize_period(self, period):
        return fields.Date.to_date(period).replace(day=1)

    @api.model
    def _get_or_create_for_assignment_period(self, assignment, period):
        normalized_period = self._normalize_period(period)
        timesheet = self.search([
            ("assignment_id", "=", assignment.id),
            ("period", "=", normalized_period),
        ], limit=1)
        if timesheet:
            return timesheet
        return self.create({
            "assignment_id": assignment.id,
            "period": normalized_period,
        })

    @api.model
    def _split_hour_vals(self, vals):
        hour_vals = {}
        clean_vals = dict(vals)
        for field_name in self._hour_field_names():
            if field_name in clean_vals:
                hour_vals[field_name] = clean_vals.pop(field_name)
        return clean_vals, hour_vals

    def _sync_line_hours(self, hour_vals):
        if not hour_vals:
            return

        Line = self.env["tenenet.project.timesheet.line"]
        for rec in self:
            existing_lines = {line.hour_type: line for line in rec.line_ids}
            for field_name, raw_value in hour_vals.items():
                hour_type = HOUR_FIELD_META[field_name]["type"]
                value = raw_value or 0.0
                line = existing_lines.get(hour_type)
                if abs(value) < 1e-9:
                    if line:
                        line.unlink()
                    continue
                if line:
                    line.hours = value
                else:
                    Line.create({
                        "timesheet_id": rec.id,
                        "hour_type": hour_type,
                        "hours": value,
                    })

    def _sync_employee_period_costs(self):
        Cost = self.env["tenenet.employee.tenenet.cost"]
        for rec in self.filtered(lambda ts: ts.employee_id and ts.period):
            Cost._sync_for_employee_period(rec.employee_id.id, rec.period)

    def _finance_monthly_comparison_pairs(self):
        return {
            (record.project_id.id, record.period.year)
            for record in self
            if record.project_id and record.period
        }

    @api.model_create_multi
    def create(self, vals_list):
        split_vals = [self._split_hour_vals(vals) for vals in vals_list]
        records = super().create([vals for vals, _hour_vals in split_vals])
        for record, (_vals, hour_vals) in zip(records, split_vals):
            record._sync_line_hours(hour_vals)
        records._sync_employee_period_costs()
        records._check_wage_cap()
        self.env["tenenet.utilization"]._recompute_for_employee_periods([
            (r.employee_id.id, r.period) for r in records if r.employee_id and r.period
        ])
        self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs(
            records._finance_monthly_comparison_pairs()
        )
        return records

    def write(self, vals):
        old_pairs = self._finance_monthly_comparison_pairs()
        clean_vals, hour_vals = self._split_hour_vals(vals)
        result = super().write(clean_vals)
        if hour_vals:
            self._sync_line_hours(hour_vals)
        if hour_vals or {"assignment_id", "period"} & set(clean_vals):
            self._sync_employee_period_costs()
        if hour_vals or {"assignment_id", "period", "wage_hm", "wage_ccp"} & set(clean_vals):
            self._check_wage_cap()
        self.env["tenenet.utilization"]._recompute_for_employee_periods([
            (r.employee_id.id, r.period) for r in self if r.employee_id and r.period
        ])
        self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs(
            old_pairs | self._finance_monthly_comparison_pairs()
        )
        return result

    def unlink(self):
        # Collect assignment+period pairs before deletion so we can re-check caps
        cap_keys = [
            (rec.assignment_id, rec.period)
            for rec in self
            if rec.assignment_id and rec.period
        ]
        sync_keys = [(rec.employee_id.id, rec.period) for rec in self if rec.employee_id and rec.period]
        finance_pairs = self._finance_monthly_comparison_pairs()
        result = super().unlink()
        Cost = self.env["tenenet.employee.tenenet.cost"]
        for employee_id, period in sync_keys:
            Cost._sync_for_employee_period(employee_id, period)
        # Re-check caps: if all timesheets for that assignment+period were deleted
        # the cap-excess entry should be removed.
        InternalExpense = self.env["tenenet.internal.expense"].sudo()
        for assignment, period in cap_keys:
            remaining = self.search([
                ("assignment_id", "=", assignment.id),
                ("period", "=", period),
            ])
            if not remaining:
                InternalExpense.search([
                    ("source_assignment_id", "=", assignment.id),
                    ("period", "=", period),
                    ("category", "=", "wage"),
                ]).unlink()
        self.env["tenenet.utilization"]._recompute_for_employee_periods(sync_keys)
        self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs(finance_pairs)
        return result

    def _check_wage_cap(self):
        """For each timesheet, check if monthly wage cap is exceeded.

        Creates/updates/deletes tenenet.internal.expense (category=wage) records.
        Skipped during hr.leave sync to avoid spurious wage expenses.
        """
        if self.env.context.get("from_hr_leave_sync"):
            return

        InternalExpense = self.env["tenenet.internal.expense"].sudo()

        for rec in self:
            assignment = rec.assignment_id
            if not assignment:
                _logger.debug("Skipping wage cap check for timesheet %s because assignment is missing.", rec.id)
                continue

            cap_hm = assignment.max_monthly_wage_hm or assignment.project_id.default_max_monthly_wage_hm or 0.0

            if cap_hm <= 0.0:
                # No cap — clean up any leftover wage expense for this assignment+period
                InternalExpense.search([
                    ("source_assignment_id", "=", assignment.id),
                    ("period", "=", rec.period),
                    ("category", "=", "wage"),
                ]).unlink()
                continue

            # Sum all timesheets for this assignment+period (including self)
            all_ts = self.search([
                ("assignment_id", "=", assignment.id),
                ("period", "=", rec.period),
            ])
            total_gross = sum(all_ts.mapped("gross_salary"))
            excess_hm = max(0.0, total_gross - cap_hm)
            _logger.info(
                "TENENET wage cap check: timesheet=%s assignment=%s project=%s period=%s cap_hm=%.4f total_gross=%.4f excess_hm=%.4f timesheet_ids=%s",
                rec.id,
                assignment.id,
                assignment.project_id.id,
                rec.period,
                cap_hm,
                total_gross,
                excess_hm,
                all_ts.ids,
            )

            existing = InternalExpense.search([
                ("source_assignment_id", "=", assignment.id),
                ("period", "=", rec.period),
                ("category", "=", "wage"),
            ], limit=1)

            if excess_hm > 0.001:
                vals = {
                    "cost_hm": excess_hm,
                    "wage_hm": assignment.wage_hm,
                    "note": f"Prekročenie mzdového stropu – priradenie {assignment.name}",
                }
                if existing:
                    _logger.info(
                        "Updating internal wage expense %s for assignment=%s period=%s with excess_hm=%.4f",
                        existing.id,
                        assignment.id,
                        rec.period,
                        excess_hm,
                    )
                    existing.write(vals)
                else:
                    _logger.info(
                        "Creating internal wage expense for assignment=%s project=%s period=%s excess_hm=%.4f",
                        assignment.id,
                        assignment.project_id.id,
                        rec.period,
                        excess_hm,
                    )
                    InternalExpense.create({
                        **vals,
                        "employee_id": assignment.employee_id.id,
                        "period": rec.period,
                        "category": "wage",
                        "source_assignment_id": assignment.id,
                        "wage_hm": assignment.wage_hm,
                    })
            else:
                if existing:
                    _logger.info(
                        "Removing internal wage expense %s for assignment=%s period=%s because excess_hm dropped to %.4f",
                        existing.id,
                        assignment.id,
                        rec.period,
                        excess_hm,
                    )
                    existing.unlink()

    @api.depends("line_ids.hour_type", "line_ids.hours")
    def _compute_hours_from_lines(self):
        for rec in self:
            totals = {field_name: 0.0 for field_name in HOUR_FIELD_META}
            for line in rec.line_ids:
                field_name = HOUR_FIELD_BY_TYPE.get(line.hour_type)
                if field_name:
                    totals[field_name] += line.hours or 0.0

            for field_name, value in totals.items():
                rec[field_name] = value

            rec.hours_project_total = sum(
                totals[field_name]
                for field_name, meta in HOUR_FIELD_META.items()
                if meta["scope"] == "project"
            )
            rec.hours_leave_total = sum(
                totals[field_name]
                for field_name, meta in HOUR_FIELD_META.items()
                if meta["scope"] == "leave"
            )
            rec.hours_total = rec.hours_project_total + rec.hours_leave_total

    def _inverse_hours_from_parent(self):
        for rec in self:
            rec._sync_line_hours({
                field_name: rec[field_name]
                for field_name in HOUR_FIELD_META
            })

    @api.depends("hours_total", "wage_hm", "wage_ccp")
    def _compute_costs(self):
        for rec in self:
            hm = rec.wage_hm or 0.0
            ccp = rec.wage_ccp or 0.0
            total = rec.hours_total or 0.0
            gross = total * hm
            rec.gross_salary = gross
            rec.deductions = gross * 0.362
            rec.total_labor_cost = total * ccp


class TenenetProjectTimesheetLine(models.Model):
    _name = "tenenet.project.timesheet.line"
    _description = "Riadok mesačného timesheetu"
    _order = "period desc, project_id, employee_id, sequence, id"

    timesheet_id = fields.Many2one(
        "tenenet.project.timesheet",
        string="Timesheet",
        required=True,
        ondelete="cascade",
    )
    assignment_id = fields.Many2one(
        "tenenet.project.assignment",
        string="Priradenie",
        related="timesheet_id.assignment_id",
        store=True,
        readonly=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        related="timesheet_id.employee_id",
        store=True,
        readonly=True,
    )
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        related="timesheet_id.project_id",
        store=True,
        readonly=True,
    )
    period = fields.Date(
        string="Obdobie",
        related="timesheet_id.period",
        store=True,
        readonly=True,
    )
    hour_type = fields.Selection(
        HOUR_TYPE_SELECTION,
        string="Typ hodín",
        required=True,
    )
    name = fields.Char(
        string="Kategória",
        compute="_compute_metadata",
        store=True,
    )
    scope = fields.Selection(
        HOUR_SCOPE_SELECTION,
        string="Skupina",
        compute="_compute_metadata",
        store=True,
    )
    sequence = fields.Integer(
        string="Poradie",
        compute="_compute_metadata",
        store=True,
    )
    hours = fields.Float(
        string="Počet hodín",
        required=True,
        digits=(10, 2),
        default=0.0,
    )

    _unique_timesheet_hour_type = models.Constraint(
        "UNIQUE(timesheet_id, hour_type)",
        "Pre timesheet môže existovať len jeden riadok pre daný typ hodín.",
    )

    @api.depends("hour_type")
    def _compute_metadata(self):
        meta_by_type = {meta["type"]: meta for meta in HOUR_FIELD_META.values()}
        for rec in self:
            meta = meta_by_type.get(rec.hour_type, {})
            rec.name = meta.get("full_label") or False
            rec.scope = meta.get("scope") or False
            rec.sequence = meta.get("sequence") or 0

    def _sync_employee_period_costs(self):
        self.mapped("timesheet_id")._sync_employee_period_costs()

    @api.model
    def _is_leave_hour_type(self, hour_type):
        return hour_type in LEAVE_HOUR_TYPES

    def _check_leave_lines_not_manually_mutated(self, vals=None):
        if self.env.context.get("from_hr_leave_sync"):
            return

        vals = vals or {}
        mutation_keys = {"hours", "hour_type", "timesheet_id"}
        targets_leave = self.filtered(lambda line: self._is_leave_hour_type(line.hour_type))
        moving_to_leave = vals.get("hour_type") and self._is_leave_hour_type(vals["hour_type"])
        if (targets_leave and (mutation_keys & set(vals))) or moving_to_leave:
            raise ValidationError(
                "Absencie (dovolenka/PN/lekár/sviatky) je možné meniť iba cez HR Dovolenky."
            )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("from_hr_leave_sync"):
            for vals in vals_list:
                if self._is_leave_hour_type(vals.get("hour_type")):
                    raise ValidationError(
                        "Absencie (dovolenka/PN/lekár/sviatky) je možné pridávať iba cez HR Dovolenky."
                    )
        records = super().create(vals_list)
        _logger.info(
            "Timesheet lines created: ids=%s timesheet_ids=%s hour_types=%s",
            records.ids,
            records.mapped("timesheet_id").ids,
            records.mapped("hour_type"),
        )
        records._sync_employee_period_costs()
        timesheets = records.mapped("timesheet_id")
        timesheets._check_wage_cap()
        self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs(
            timesheets._finance_monthly_comparison_pairs()
        )
        return records

    def write(self, vals):
        self._check_leave_lines_not_manually_mutated(vals)
        old_timesheets = self.mapped("timesheet_id")
        result = super().write(vals)
        impacted_timesheets = old_timesheets | self.mapped("timesheet_id")
        _logger.info(
            "Timesheet lines updated: ids=%s impacted_timesheet_ids=%s vals=%s",
            self.ids,
            impacted_timesheets.ids,
            vals,
        )
        impacted_timesheets._sync_employee_period_costs()
        impacted_timesheets._check_wage_cap()
        self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs(
            (old_timesheets | impacted_timesheets)._finance_monthly_comparison_pairs()
        )
        return result

    def unlink(self):
        self._check_leave_lines_not_manually_mutated({"hours": 0.0})
        timesheets = self.mapped("timesheet_id")
        result = super().unlink()
        _logger.info(
            "Timesheet lines deleted from timesheet_ids=%s",
            timesheets.ids,
        )
        timesheets._sync_employee_period_costs()
        timesheets._check_wage_cap()
        self.env["tenenet.project"]._sync_finance_monthly_comparison_pairs(
            timesheets._finance_monthly_comparison_pairs()
        )
        return result
