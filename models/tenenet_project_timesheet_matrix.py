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
    year_picker = fields.Selection(
        selection="_selection_year_picker",
        string="Prepnúť rok",
    )

    _unique_assignment_year = models.Constraint(
        "UNIQUE(assignment_id, year)",
        "Pre priradenie môže existovať iba jedna matica za rok.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if not record.year_picker:
                record.year_picker = str(record.year)
        records._ensure_line_rows()
        records._load_from_timesheets()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "assignment_id" in vals or "year" in vals:
            self._ensure_line_rows()
            self._load_from_timesheets()
        if "year" in vals and "year_picker" not in vals:
            for record in self:
                record.year_picker = str(record.year)
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
        # Priority 1: Context with explicit year options
        years = self.env.context.get("matrix_year_options")
        if years:
            return [(str(year), str(year)) for year in years]
        
        # Priority 2: If we have a record with an assignment, get expected years
        if self and self.assignment_id:
            expected_years = self.assignment_id._get_expected_years()
            if expected_years:
                # Ensure current year is included
                if self.year and self.year not in expected_years:
                    expected_years = sorted(set(expected_years + [self.year]))
                return [(str(year), str(year)) for year in expected_years]
        
        # Priority 3: Use the record's year if available
        if self and self.year:
            return [(str(self.year), str(self.year))]
        
        # Priority 4: Fall back to current year only as last resort
        current_year = fields.Date.today().year
        return [(str(current_year), str(current_year))]

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
        # Always set year_picker to the matrix's year
        self.year_picker = str(self.year)
        year_options = expected_years or sorted(self.assignment_id.matrix_ids.mapped("year"))
        if self.year not in year_options:
            year_options = sorted(set(year_options + [self.year]))
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
            "context": {
                **self.env.context,
                "matrix_year_options": year_options,
            },
        }

    def action_open_selected_year(self):
        self.ensure_one()
        selected_year = int(self.year_picker or self.year)
        matrix = self._ensure_for_assignment_years(
            self.assignment_id,
            [selected_year],
        ).filtered(lambda rec: rec.year == selected_year)[:1]
        return matrix.action_open_form()

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
