from datetime import date

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .tenenet_project_timesheet import HOUR_FIELD_META, HOUR_SCOPE_SELECTION, HOUR_TYPE_SELECTION


MONTH_LABELS = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "Máj",
    6: "Jún",
    7: "Júl",
    8: "Aug",
    9: "Sep",
    10: "Okt",
    11: "Nov",
    12: "Dec",
}


class TenenetProjectTimesheetMatrix(models.Model):
    _name = "tenenet.project.timesheet.matrix"
    _description = "Ročná matica timesheetu priradenia"
    _order = "year desc, project_id, employee_id"
    _rec_name = "name"

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
    year = fields.Integer(
        string="Rok",
        required=True,
        default=lambda self: fields.Date.today().year,
    )
    name = fields.Char(
        string="Názov",
        compute="_compute_name",
        store=True,
    )
    line_ids = fields.One2many(
        "tenenet.project.timesheet.matrix.line",
        "matrix_id",
        string="Riadky matice",
    )
    # Year navigation
    can_go_previous = fields.Boolean(
        string="Môže ísť späť",
        compute="_compute_year_navigation",
    )
    can_go_next = fields.Boolean(
        string="Môže ísť ďalej",
        compute="_compute_year_navigation",
    )
    previous_year = fields.Integer(
        string="Predchádzajúci rok",
        compute="_compute_year_navigation",
    )
    next_year = fields.Integer(
        string="Nasledujúci rok",
        compute="_compute_year_navigation",
    )
    # Monthly totals (computed from line_ids)
    total_month_01 = fields.Float(string=MONTH_LABELS[1], compute="_compute_monthly_totals", digits=(10, 2))
    total_month_02 = fields.Float(string=MONTH_LABELS[2], compute="_compute_monthly_totals", digits=(10, 2))
    total_month_03 = fields.Float(string=MONTH_LABELS[3], compute="_compute_monthly_totals", digits=(10, 2))
    total_month_04 = fields.Float(string=MONTH_LABELS[4], compute="_compute_monthly_totals", digits=(10, 2))
    total_month_05 = fields.Float(string=MONTH_LABELS[5], compute="_compute_monthly_totals", digits=(10, 2))
    total_month_06 = fields.Float(string=MONTH_LABELS[6], compute="_compute_monthly_totals", digits=(10, 2))
    total_month_07 = fields.Float(string=MONTH_LABELS[7], compute="_compute_monthly_totals", digits=(10, 2))
    total_month_08 = fields.Float(string=MONTH_LABELS[8], compute="_compute_monthly_totals", digits=(10, 2))
    total_month_09 = fields.Float(string=MONTH_LABELS[9], compute="_compute_monthly_totals", digits=(10, 2))
    total_month_10 = fields.Float(string=MONTH_LABELS[10], compute="_compute_monthly_totals", digits=(10, 2))
    total_month_11 = fields.Float(string=MONTH_LABELS[11], compute="_compute_monthly_totals", digits=(10, 2))
    total_month_12 = fields.Float(string=MONTH_LABELS[12], compute="_compute_monthly_totals", digits=(10, 2))

    _unique_assignment_year = models.Constraint(
        "UNIQUE(assignment_id, year)",
        "Pre priradenie môže existovať iba jedna matica za rok.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_line_rows()
        records._load_from_timesheets()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "assignment_id" in vals or "year" in vals:
            self._ensure_line_rows()
            self._load_from_timesheets()
        return result

    def _ensure_line_rows(self):
        Line = self.env["tenenet.project.timesheet.matrix.line"]
        for rec in self:
            existing_types = set(rec.line_ids.mapped("hour_type"))
            for field_name, meta in sorted(
                HOUR_FIELD_META.items(),
                key=lambda item: item[1]["sequence"],
            ):
                if meta["type"] in existing_types:
                    continue
                Line.create({
                    "matrix_id": rec.id,
                    "hour_type": meta["type"],
                })

    @api.model
    def _ensure_for_assignment_years(self, assignment, years):
        if not assignment:
            return self.browse()

        existing = self.search([
            ("assignment_id", "=", assignment.id),
            ("year", "in", list(years)),
        ])
        matrix_by_year = {matrix.year: matrix for matrix in existing}
        missing_vals = [
            {
                "assignment_id": assignment.id,
                "year": year,
            }
            for year in years
            if year not in matrix_by_year
        ]
        created = self.create(missing_vals) if missing_vals else self.browse()
        return existing | created

    def _selection_year_picker(self):
        # Kept for backward compatibility, not used in UI anymore
        if self and self.year:
            return [(str(self.year), str(self.year))]
        current_year = fields.Date.today().year
        return [(str(current_year), str(current_year))]

    @api.depends("year", "assignment_id.date_start", "assignment_id.date_end")
    def _compute_year_navigation(self):
        for rec in self:
            expected_years = rec.assignment_id._get_expected_years() if rec.assignment_id else []
            if not expected_years:
                expected_years = [rec.year] if rec.year else []
            
            rec.previous_year = rec.year - 1 if rec.year else 0
            rec.next_year = rec.year + 1 if rec.year else 0
            rec.can_go_previous = rec.previous_year in expected_years
            rec.can_go_next = rec.next_year in expected_years

    @api.depends("line_ids.month_01", "line_ids.month_02", "line_ids.month_03",
                 "line_ids.month_04", "line_ids.month_05", "line_ids.month_06",
                 "line_ids.month_07", "line_ids.month_08", "line_ids.month_09",
                 "line_ids.month_10", "line_ids.month_11", "line_ids.month_12")
    def _compute_monthly_totals(self):
        for rec in self:
            for month in range(1, 13):
                field_name = f"month_{month:02d}"
                total_field = f"total_{field_name}"
                total = sum(line[field_name] or 0.0 for line in rec.line_ids)
                rec[total_field] = total

    @api.depends("project_id.name", "employee_id.name", "year")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.project_id.name or '-'} / {rec.employee_id.name or '-'} / {rec.year or ''}"

    def _load_from_timesheets(self):
        for rec in self:
            rec.line_ids._load_month_values_from_timesheets()

    def action_open_form(self):
        self.ensure_one()
        self.assignment_id._sync_precreated_timesheets()
        expected_years = self.assignment_id._get_expected_years()
        if expected_years:
            self._ensure_for_assignment_years(self.assignment_id, expected_years)
        self._load_from_timesheets()
        return {
            "type": "ir.actions.act_window",
            "name": "Mesačná matica hodín",
            "res_model": "tenenet.project.timesheet.matrix",
            "view_mode": "form",
            "views": [
                (self.env.ref("tenenet_projects.view_tenenet_project_timesheet_matrix_form").id, "form")
            ],
            "res_id": self.id,
            "target": "current",
        }

    def _action_open_year(self, target_year):
        """Open the matrix for the specified year."""
        self.ensure_one()
        matrix = self._ensure_for_assignment_years(
            self.assignment_id,
            [target_year],
        ).filtered(lambda rec: rec.year == target_year)[:1]
        if matrix:
            return matrix.action_open_form()
        return self.action_open_form()

    def action_previous_year(self):
        """Navigate to the previous year's matrix."""
        self.ensure_one()
        if self.can_go_previous:
            return self._action_open_year(self.previous_year)
        return self.action_open_form()

    def action_next_year(self):
        """Navigate to the next year's matrix."""
        self.ensure_one()
        if self.can_go_next:
            return self._action_open_year(self.next_year)
        return self.action_open_form()

    def name_get(self):
        return [
            (
                rec.id,
                f"{rec.project_id.name or '-'} / {rec.employee_id.name or '-'} / {rec.year}",
            )
            for rec in self
        ]


class TenenetProjectTimesheetMatrixLine(models.Model):
    _name = "tenenet.project.timesheet.matrix.line"
    _description = "Riadok ročnej matice timesheetu"
    _order = "employee_id, sequence, id"

    matrix_id = fields.Many2one(
        "tenenet.project.timesheet.matrix",
        string="Matica",
        required=True,
        ondelete="cascade",
    )
    assignment_id = fields.Many2one(
        "tenenet.project.assignment",
        string="Priradenie",
        related="matrix_id.assignment_id",
        store=True,
        readonly=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        related="matrix_id.employee_id",
        store=True,
        readonly=True,
    )
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        related="matrix_id.project_id",
        store=True,
        readonly=True,
    )
    year = fields.Integer(
        string="Rok",
        related="matrix_id.year",
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
    month_01 = fields.Float(string=MONTH_LABELS[1], digits=(10, 2), default=0.0)
    month_02 = fields.Float(string=MONTH_LABELS[2], digits=(10, 2), default=0.0)
    month_03 = fields.Float(string=MONTH_LABELS[3], digits=(10, 2), default=0.0)
    month_04 = fields.Float(string=MONTH_LABELS[4], digits=(10, 2), default=0.0)
    month_05 = fields.Float(string=MONTH_LABELS[5], digits=(10, 2), default=0.0)
    month_06 = fields.Float(string=MONTH_LABELS[6], digits=(10, 2), default=0.0)
    month_07 = fields.Float(string=MONTH_LABELS[7], digits=(10, 2), default=0.0)
    month_08 = fields.Float(string=MONTH_LABELS[8], digits=(10, 2), default=0.0)
    month_09 = fields.Float(string=MONTH_LABELS[9], digits=(10, 2), default=0.0)
    month_10 = fields.Float(string=MONTH_LABELS[10], digits=(10, 2), default=0.0)
    month_11 = fields.Float(string=MONTH_LABELS[11], digits=(10, 2), default=0.0)
    month_12 = fields.Float(string=MONTH_LABELS[12], digits=(10, 2), default=0.0)
    month_01_editable = fields.Boolean(compute="_compute_month_editability", store=True)
    month_02_editable = fields.Boolean(compute="_compute_month_editability", store=True)
    month_03_editable = fields.Boolean(compute="_compute_month_editability", store=True)
    month_04_editable = fields.Boolean(compute="_compute_month_editability", store=True)
    month_05_editable = fields.Boolean(compute="_compute_month_editability", store=True)
    month_06_editable = fields.Boolean(compute="_compute_month_editability", store=True)
    month_07_editable = fields.Boolean(compute="_compute_month_editability", store=True)
    month_08_editable = fields.Boolean(compute="_compute_month_editability", store=True)
    month_09_editable = fields.Boolean(compute="_compute_month_editability", store=True)
    month_10_editable = fields.Boolean(compute="_compute_month_editability", store=True)
    month_11_editable = fields.Boolean(compute="_compute_month_editability", store=True)
    month_12_editable = fields.Boolean(compute="_compute_month_editability", store=True)

    _unique_matrix_hour_type = models.Constraint(
        "UNIQUE(matrix_id, hour_type)",
        "Pre maticu môže existovať iba jeden riadok pre daný typ hodín.",
    )

    @api.depends("hour_type")
    def _compute_metadata(self):
        meta_by_type = {meta["type"]: meta for meta in HOUR_FIELD_META.values()}
        for rec in self:
            meta = meta_by_type.get(rec.hour_type, {})
            rec.name = meta.get("full_label") or False
            rec.scope = meta.get("scope") or False
            rec.sequence = meta.get("sequence") or 0

    @api.depends(
        "year",
        "assignment_id.date_start",
        "assignment_id.date_end",
        "assignment_id.project_id.date_start",
        "assignment_id.project_id.date_end",
    )
    def _compute_month_editability(self):
        for rec in self:
            for month in range(1, 13):
                editable = False
                if rec.assignment_id and rec.year:
                    editable = rec.assignment_id._is_period_in_scope(date(rec.year, month, 1))
                rec[f"month_{month:02d}_editable"] = editable

    def _load_month_values_from_timesheets(self):
        for rec in self:
            values = {month: 0.0 for month in range(1, 13)}
            relevant_timesheets = rec.assignment_id.timesheet_ids.filtered(
                lambda timesheet: timesheet.period and timesheet.period.year == rec.year
            )
            for timesheet in relevant_timesheets:
                line = timesheet.line_ids.filtered(lambda item: item.hour_type == rec.hour_type)[:1]
                if line and timesheet.period:
                    values[timesheet.period.month] = line.hours or 0.0

            rec.with_context(skip_matrix_month_sync=True).write({
                f"month_{month:02d}": values[month]
                for month in range(1, 13)
            })

    def _sync_month_values_to_timesheets(self, month_field_names):
        Timesheet = self.env["tenenet.project.timesheet"]
        Line = self.env["tenenet.project.timesheet.line"]

        for rec in self:
            rec.assignment_id._sync_precreated_timesheets()
            for field_name in month_field_names:
                month = int(field_name.split("_")[1])
                period = date(rec.year, month, 1)
                timesheet = Timesheet._get_or_create_for_assignment_period(rec.assignment_id, period)
                value = rec[field_name] or 0.0
                existing_line = timesheet.line_ids.filtered(
                    lambda line: line.hour_type == rec.hour_type
                )[:1]
                if abs(value) < 1e-9:
                    if existing_line:
                        existing_line.unlink()
                    continue
                if existing_line:
                    existing_line.hours = value
                else:
                    Line.create({
                        "timesheet_id": timesheet.id,
                        "hour_type": rec.hour_type,
                        "hours": value,
                    })

    def _validate_month_writes_in_scope(self, vals):
        month_field_names = [field_name for field_name in vals if field_name.startswith("month_")]
        if not month_field_names:
            return

        for rec in self:
            for field_name in month_field_names:
                editable_field = f"{field_name}_editable"
                if not rec[editable_field]:
                    new_value = vals.get(field_name, 0.0) or 0.0
                    old_value = rec[field_name] or 0.0
                    if abs(new_value - old_value) > 1e-9:
                        month_label = MONTH_LABELS[int(field_name.split("_")[1])]
                        raise ValidationError(
                            f"Mesiac {month_label} {rec.year} je mimo rozsahu priradenia a nie je možné ho upravovať."
                        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._load_month_values_from_timesheets()
        return records

    def write(self, vals):
        if not self.env.context.get("skip_matrix_month_sync"):
            self._validate_month_writes_in_scope(vals)
        result = super().write(vals)
        if self.env.context.get("skip_matrix_month_sync"):
            return result
        month_field_names = [field_name for field_name in vals if field_name.startswith("month_")]
        if month_field_names:
            self._sync_month_values_to_timesheets(month_field_names)
            self.flush_recordset(month_field_names)
            self.invalidate_recordset(month_field_names)
            self._load_month_values_from_timesheets()
        return result
