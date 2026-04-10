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

HOUR_TYPE_ORDER = {
    "pp": 10,
    "np": 20,
    "travel": 30,
    "training": 40,
    "ambulance": 50,
    "international": 60,
    "vacation": 70,
    "sick": 80,
    "doctor": 90,
    "holidays": 100,
    "total": 9999,
}

# Extended hour type selection with total row
MATRIX_HOUR_TYPE_SELECTION = HOUR_TYPE_SELECTION + [("total", "SPOLU")]


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
            # Create hour type rows
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
            # Create total row (always last, sequence 9999)
            if "total" not in existing_types:
                Line.create({
                    "matrix_id": rec.id,
                    "hour_type": "total",
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

    @api.depends("project_id.name", "employee_id.name", "year")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.project_id.name or '-'} / {rec.employee_id.name or '-'} / {rec.year or ''}"

    def _load_from_timesheets(self):
        for rec in self:
            rec.line_ids._load_month_values_from_timesheets()

    @api.model
    def _refresh_for_assignment_periods(self, assignment_periods):
        """Persist matrix line and grid-entry values for the affected assignment/year pairs."""
        if not assignment_periods:
            return self.browse()

        Assignment = self.env["tenenet.project.assignment"].sudo()
        refreshed = self.browse()
        years_by_assignment = {}
        for assignment_id, period in assignment_periods:
            period_date = fields.Date.to_date(period) if period else False
            if not assignment_id or not period_date:
                continue
            years_by_assignment.setdefault(assignment_id, set()).add(period_date.year)

        for assignment_id, years in years_by_assignment.items():
            assignment = Assignment.browse(assignment_id).exists()
            if not assignment or not years:
                continue
            matrices = self.sudo()._ensure_for_assignment_years(assignment, sorted(years))
            if matrices:
                matrices._load_from_timesheets()
                refreshed |= matrices
        return refreshed

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

    def action_open_grid(self):
        self.ensure_one()
        self.assignment_id._sync_precreated_timesheets()
        expected_years = self.assignment_id._get_expected_years()
        if expected_years:
            self._ensure_for_assignment_years(self.assignment_id, expected_years)
        self._load_from_timesheets()
        action = self.env.ref("tenenet_projects.action_tenenet_project_timesheet_matrix_grid").read()[0]
        action["domain"] = [("matrix_id", "=", self.id)]
        action["context"] = {
            **dict(self.env.context),
            "default_matrix_id": self.id,
            "grid_anchor": f"{self.year}-01-01",
            "auto_sync_timesheet_matrix_entries": True,
        }
        return action

    def _action_open_year(self, target_year):
        """Open the matrix for the specified year."""
        self.ensure_one()
        matrix = self._ensure_for_assignment_years(
            self.assignment_id,
            [target_year],
        ).filtered(lambda rec: rec.year == target_year)[:1]
        if matrix:
            return matrix.action_open_grid()
        return self.action_open_grid()

    def action_previous_year(self):
        """Navigate to the previous year's matrix."""
        self.ensure_one()
        if self.can_go_previous:
            return self._action_open_year(self.previous_year)
        return self.action_open_grid()

    def action_next_year(self):
        """Navigate to the next year's matrix."""
        self.ensure_one()
        if self.can_go_next:
            return self._action_open_year(self.next_year)
        return self.action_open_grid()

    @api.model
    def sync_my_matrices(self):
        """Sync matrices for the current user and return their employee ID.

        Also ensures matrices exist for any year that already has timesheets,
        covering the case where timesheets were entered outside the assignment
        date range (which _get_expected_periods would otherwise miss).

        Returns the employee ID (int) so the client can filter without relying
        on the employee→user link being traversable in a domain.
        """
        employee = self.env["hr.employee"].search([("user_id", "=", self.env.uid)], limit=1)
        if not employee:
            return False
        assignments = self.env["tenenet.project.assignment"].search(
            [("employee_id", "=", employee.id)]
        )
        assignments._sync_precreated_timesheets()
        # Ensure matrices for any year that already has timesheet records,
        # even if those years fall outside the stored assignment date range.
        for assignment in assignments:
            extra_years = {ts.period.year for ts in assignment.timesheet_ids if ts.period}
            if extra_years:
                self._ensure_for_assignment_years(assignment, sorted(extra_years))
        return employee.id

    @api.model
    def get_garant_projects(self):
        """Return projects for the garant/PM view.

        Managers see all active projects; garanti/PMs see only their own.
        """
        if self.env.user.has_group("tenenet_projects.group_tenenet_manager"):
            projects = self.env["tenenet.project"].search(
                [("active", "=", True), ("is_tenenet_internal", "=", False)],
                order="name",
            )
        else:
            employee = self.env["hr.employee"].search([("user_id", "=", self.env.uid)], limit=1)
            if not employee:
                return []
            projects = self.env["tenenet.project"].search([
                ("active", "=", True),
                ("is_tenenet_internal", "=", False),
                "|",
                ("odborny_garant_id", "=", employee.id),
                ("project_manager_id", "=", employee.id),
            ], order="name")
        return [{"id": p.id, "name": p.name, "code": ""} for p in projects]

    @api.model
    def action_open_my_matrices(self):
        """Sync assignments for the current user, then return the matrix list action."""
        employee = self.env["hr.employee"].search([("user_id", "=", self.env.uid)], limit=1)
        if employee:
            assignments = self.env["tenenet.project.assignment"].search(
                [("employee_id", "=", employee.id)]
            )
            assignments._sync_precreated_timesheets()
        return {
            "type": "ir.actions.act_window",
            "name": "Moje timesheety",
            "res_model": "tenenet.project.timesheet.matrix",
            "view_mode": "list,form",
            "views": [
                (self.env.ref("tenenet_projects.view_tenenet_project_timesheet_matrix_my_list").id, "list"),
                (self.env.ref("tenenet_projects.view_tenenet_project_timesheet_matrix_form").id, "form"),
            ],
            "domain": [("employee_id.user_id", "=", self.env.uid)],
            "context": {"search_default_current_year": 1},
        }

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
        MATRIX_HOUR_TYPE_SELECTION,
        string="Typ hodín",
        required=True,
    )
    is_total = fields.Boolean(
        string="Je súčtový riadok",
        compute="_compute_metadata",
        store=True,
    )
    leave_sync_managed = fields.Boolean(
        string="Absencia spravovaná HR",
        compute="_compute_metadata",
        store=True,
    )
    name = fields.Char(
        string="Kategória",
        compute="_compute_metadata",
        store=True,
    )
    scope = fields.Selection(
        HOUR_SCOPE_SELECTION + [("total", "Súčet")],
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
    entry_ids = fields.One2many(
        "tenenet.project.timesheet.matrix.entry",
        "line_id",
        string="Mesačné bunky",
    )

    _unique_matrix_hour_type = models.Constraint(
        "UNIQUE(matrix_id, hour_type)",
        "Pre maticu môže existovať iba jeden riadok pre daný typ hodín.",
    )

    @api.depends("hour_type")
    def _compute_metadata(self):
        meta_by_type = {meta["type"]: meta for meta in HOUR_FIELD_META.values()}
        for rec in self:
            if rec.hour_type == "total":
                rec.name = "SPOLU"
                rec.scope = "total"
                rec.sequence = 9999
                rec.is_total = True
                rec.leave_sync_managed = False
            else:
                meta = meta_by_type.get(rec.hour_type, {})
                rec.name = meta.get("full_label") or False
                rec.scope = meta.get("scope") or False
                rec.sequence = meta.get("sequence") or 0
                rec.is_total = False
                rec.leave_sync_managed = rec.scope == "leave"

    @api.depends(
        "hour_type",
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
                # Total row is never editable
                if rec.hour_type != "total" and rec.assignment_id and rec.year:
                    editable = rec.assignment_id._is_period_in_scope(date(rec.year, month, 1))
                rec[f"month_{month:02d}_editable"] = editable

    def _load_month_values_from_timesheets(self):
        for rec in self:
            # Skip total rows - they are computed separately
            if rec.hour_type == "total":
                continue
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
        # Update total rows after loading data
        self._update_total_rows()

    def _update_total_rows(self):
        """Update total row values based on sum of all other rows in the matrix."""
        matrices = self.mapped("matrix_id")
        for matrix in matrices:
            total_line = matrix.line_ids.filtered(lambda l: l.hour_type == "total")[:1]
            if not total_line:
                continue
            data_lines = matrix.line_ids.filtered(lambda l: l.hour_type != "total")
            totals = {}
            for month in range(1, 13):
                field_name = f"month_{month:02d}"
                totals[field_name] = sum(line[field_name] or 0.0 for line in data_lines)
            total_line.with_context(skip_matrix_month_sync=True).write(totals)

    def _sync_grid_entries(self):
        Entry = self.env["tenenet.project.timesheet.matrix.entry"]
        for rec in self.filtered(lambda line: line.year):
            existing_entries = {entry.period: entry for entry in rec.entry_ids}
            desired_periods = set()
            for month in range(1, 13):
                period = date(rec.year, month, 1)
                desired_periods.add(period)
                values = {
                    "line_id": rec.id,
                    "period": period,
                    "hours": rec[f"month_{month:02d}"] or 0.0,
                    "editable": bool(
                        rec[f"month_{month:02d}_editable"]
                        and not rec.leave_sync_managed
                        and not rec.is_total
                    ),
                }
                existing_entry = existing_entries.get(period)
                if existing_entry:
                    existing_entry.with_context(skip_matrix_entry_sync=True).write(values)
                else:
                    Entry.with_context(skip_matrix_entry_sync=True).create(values)
            stale_entries = rec.entry_ids.filtered(lambda entry: entry.period not in desired_periods)
            if stale_entries:
                stale_entries.unlink()

    def _sync_month_values_to_timesheets(self, month_field_names):
        Timesheet = self.env["tenenet.project.timesheet"]
        Line = self.env["tenenet.project.timesheet.line"]

        for rec in self:
            # Skip total rows - they don't sync to timesheets
            if rec.hour_type == "total" or rec.scope == "leave":
                continue
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
            if rec.scope == "leave":
                for field_name in month_field_names:
                    new_value = vals.get(field_name, 0.0) or 0.0
                    old_value = rec[field_name] or 0.0
                    if abs(new_value - old_value) > 1e-9:
                        raise ValidationError(
                            "Riadky absencií sú spravované iba cez HR Dovolenky a nie je možné ich ručne upravovať v matici."
                        )
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
        # Load values for non-total rows, then update totals
        non_total_records = records.filtered(lambda r: r.hour_type != "total")
        non_total_records._load_month_values_from_timesheets()
        # Ensure total rows are updated
        records._update_total_rows()
        records._sync_grid_entries()
        return records

    def write(self, vals):
        if not self.env.context.get("skip_matrix_month_sync"):
            self._validate_month_writes_in_scope(vals)
        result = super().write(vals)
        if self.env.context.get("skip_matrix_month_sync"):
            self._sync_grid_entries()
            return result
        month_field_names = [field_name for field_name in vals if field_name.startswith("month_")]
        if month_field_names:
            self._sync_month_values_to_timesheets(month_field_names)
            self.flush_recordset(month_field_names)
            self.invalidate_recordset(month_field_names)
            self._load_month_values_from_timesheets()
        self._sync_grid_entries()
        return result


class TenenetProjectTimesheetMatrixEntry(models.Model):
    _name = "tenenet.project.timesheet.matrix.entry"
    _description = "Mesačná bunka ročnej matice timesheetu"
    _order = "matrix_id, sequence, period, id"
    _rec_name = "name"

    line_id = fields.Many2one(
        "tenenet.project.timesheet.matrix.line",
        string="Riadok matice",
        required=True,
        ondelete="cascade",
    )
    matrix_id = fields.Many2one(
        "tenenet.project.timesheet.matrix",
        string="Matica",
        related="line_id.matrix_id",
        store=True,
        readonly=True,
    )
    assignment_id = fields.Many2one(
        "tenenet.project.assignment",
        string="Priradenie",
        related="line_id.assignment_id",
        store=True,
        readonly=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        related="line_id.employee_id",
        store=True,
        readonly=True,
    )
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        related="line_id.project_id",
        store=True,
        readonly=True,
    )
    year = fields.Integer(
        string="Rok",
        related="line_id.year",
        store=True,
        readonly=True,
    )
    hour_type = fields.Selection(
        MATRIX_HOUR_TYPE_SELECTION,
        string="Typ hodín",
        related="line_id.hour_type",
        store=True,
        readonly=True,
    )
    is_total = fields.Boolean(
        string="Je súčtový riadok",
        related="line_id.is_total",
        store=True,
        readonly=True,
    )
    leave_sync_managed = fields.Boolean(
        string="Absencia spravovaná HR",
        related="line_id.leave_sync_managed",
        store=True,
        readonly=True,
    )
    name = fields.Char(
        string="Kategória",
        related="line_id.name",
        store=True,
        readonly=True,
    )
    scope = fields.Selection(
        HOUR_SCOPE_SELECTION + [("total", "Súčet")],
        string="Skupina",
        related="line_id.scope",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(
        string="Poradie",
        related="line_id.sequence",
        store=True,
        readonly=True,
    )
    period = fields.Date(
        string="Obdobie",
        required=True,
    )
    month = fields.Integer(
        string="Mesiac",
        compute="_compute_month",
        store=True,
    )
    hours = fields.Float(
        string="Hodiny",
        digits=(10, 2),
        default=0.0,
    )
    editable = fields.Boolean(
        string="Editovateľné",
        default=False,
    )

    _unique_line_period = models.Constraint(
        "UNIQUE(line_id, period)",
        "Pre rovnaký riadok a mesiac môže existovať len jedna bunka matice.",
    )

    @api.depends("period")
    def _compute_month(self):
        for rec in self:
            rec.month = rec.period.month if rec.period else 0

    @api.model
    def _auto_sync_grid_matrix(self):
        if self.env.context.get("_timesheet_matrix_entry_autosync_done"):
            return
        if not self.env.context.get("auto_sync_timesheet_matrix_entries"):
            return
        matrix_id = self.env.context.get("default_matrix_id")
        if not matrix_id:
            return
        matrix = self.env["tenenet.project.timesheet.matrix"].browse(matrix_id).exists()
        if matrix:
            matrix.line_ids.with_context(
                _timesheet_matrix_entry_autosync_done=True
            )._sync_grid_entries()

    def _is_effectively_editable(self):
        self.ensure_one()
        if self.leave_sync_managed or self.is_total:
            return False
        return bool(self.line_id[f"month_{self.month:02d}_editable"])

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        self._auto_sync_grid_matrix()
        return super().search(domain, offset=offset, limit=limit, order=order)

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        self._auto_sync_grid_matrix()
        return super().read_group(
            domain,
            fields,
            groupby,
            offset=offset,
            limit=limit,
            orderby=orderby,
            lazy=lazy,
        )

    @api.model
    def formatted_read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None):
        self._auto_sync_grid_matrix()
        result = super().formatted_read_group(
            domain, groupby=groupby, aggregates=aggregates, having=having,
            offset=offset, limit=limit, order=order,
        )
        if 'hour_type' in groupby:
            result = sorted(result, key=lambda g: HOUR_TYPE_ORDER.get(g.get('hour_type'), 9999))
        return result

    @api.model
    def read_grid(self, domain, row_fields, col_field, cell_field, range):
        self._auto_sync_grid_matrix()
        result = super().read_grid(domain, row_fields, col_field, cell_field, range)
        row_titles = result.get("row_titles", [])
        data_rows = result.get("data", [])
        sorted_rows = []
        for row_title, row in zip(row_titles, data_rows):
            row_values = row_title.get("values", {})
            hour_type_info = row_values.get("hour_type") or [False, ""]
            row_order = HOUR_TYPE_ORDER.get(hour_type_info[0], 9999)
            sorted_rows.append((row_order, row_title, row))
            for cell in row:
                record = self.search(cell.get("domain", []), limit=1)
                if not record:
                    cell["readonly"] = True
                    continue
                cell["readonly"] = not record.editable
                if record.is_total:
                    cell.setdefault("classes", []).append("text-info")
                if record.scope == "leave":
                    cell.setdefault("classes", []).append("o_tenenet_grid_leave_cell")
                if record.scope == "total":
                    cell.setdefault("classes", []).append("o_tenenet_grid_total_cell")
        if sorted_rows:
            sorted_rows.sort(key=lambda item: (item[0],))
            result["row_titles"] = [item[1] for item in sorted_rows]
            result["data"] = [item[2] for item in sorted_rows]
        return result

    @api.model
    def grid_update_cell(self, domain, measure_field_name, value):
        if measure_field_name != "hours" or value == 0:
            return False
        entry = self.search(domain, limit=1)
        if not entry:
            return False
        if not entry._is_effectively_editable():
            raise ValidationError(
                "Tento typ hodín je spravovaný automaticky alebo je mimo rozsahu priradenia a nie je možné ho upravovať v matici."
            )
        month_field_name = f"month_{entry.month:02d}"
        entry.line_id.write({
            month_field_name: (entry.hours or 0.0) + value,
        })
        return {"type": "ir.actions.client", "tag": "reload"}

    def write(self, vals):
        if self.env.context.get("skip_matrix_entry_sync") or "hours" not in vals:
            return super().write(vals)

        for rec in self:
            if not rec._is_effectively_editable():
                raise ValidationError(
                    "Tento typ hodín je spravovaný automaticky alebo je mimo rozsahu priradenia a nie je možné ho upravovať v matici."
                )
            rec.line_id.with_context(skip_matrix_entry_sync=True).write({
                f"month_{rec.month:02d}": vals["hours"] or 0.0,
            })
        return True
