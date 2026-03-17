from datetime import date

from odoo import Command, api, fields, models

from ..models.tenenet_project_timesheet import HOUR_FIELD_META


MONTH_FIELD_NAMES = tuple(f"month_{month:02d}" for month in range(1, 13))
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


class TenenetProjectTimesheetMatrixWizard(models.TransientModel):
    _name = "tenenet.project.timesheet.matrix.wizard"
    _description = "Mesačná matica timesheetu projektu"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
    )
    year = fields.Integer(
        string="Rok",
        required=True,
        default=lambda self: fields.Date.today().year,
    )
    line_ids = fields.One2many(
        "tenenet.project.timesheet.matrix.wizard.line",
        "wizard_id",
        string="Riadky matice",
    )

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if "project_id" in fields_list and not vals.get("project_id"):
            active_model = self.env.context.get("active_model")
            active_id = self.env.context.get("active_id")
            if active_model == "tenenet.project" and active_id:
                vals["project_id"] = active_id
        if "year" in fields_list and not vals.get("year") and vals.get("project_id"):
            project = self.env["tenenet.project"].browse(vals["project_id"])
            vals["year"] = project.active_year_from or project.year or fields.Date.today().year
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record, vals in zip(records, vals_list):
            if not vals.get("line_ids"):
                record._rebuild_lines()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "project_id" in vals or "year" in vals:
            for wizard in self:
                wizard._rebuild_lines()
        return result

    @api.onchange("project_id", "year")
    def _onchange_project_or_year(self):
        if self.project_id and self.year:
            self._rebuild_lines()
        else:
            self.line_ids = [Command.clear()]

    def _rebuild_lines(self):
        self.ensure_one()
        if not self.project_id or not self.year:
            self.line_ids = [Command.clear()]
            return

        line_model = self.env["tenenet.project.timesheet.line"]
        period_from = date(self.year, 1, 1)
        period_to = date(self.year, 12, 1)
        existing_lines = line_model.search([
            ("project_id", "=", self.project_id.id),
            ("period", ">=", period_from),
            ("period", "<=", period_to),
        ])
        hours_by_key = {
            (line.assignment_id.id, line.hour_type, line.period.month): line.hours
            for line in existing_lines
        }

        commands = [Command.clear()]
        assignments = self.project_id.assignment_ids.sorted(
            key=lambda assignment: (
                assignment.employee_id.name or "",
                assignment.id,
            )
        )
        for assignment in assignments:
            for field_name, meta in sorted(
                HOUR_FIELD_META.items(),
                key=lambda item: item[1]["sequence"],
            ):
                row_vals = {
                    "assignment_id": assignment.id,
                    "employee_id": assignment.employee_id.id,
                    "hour_type": meta["type"],
                    "name": meta["full_label"],
                    "scope": meta["scope"],
                    "sequence": meta["sequence"],
                }
                for month in range(1, 13):
                    row_vals[f"month_{month:02d}"] = hours_by_key.get(
                        (assignment.id, meta["type"], month),
                        0.0,
                    )
                commands.append(Command.create(row_vals))
        self.line_ids = commands

    def action_apply(self):
        self.ensure_one()
        Timesheet = self.env["tenenet.project.timesheet"]
        Line = self.env["tenenet.project.timesheet.line"]

        existing_timesheets = Timesheet.search([
            ("project_id", "=", self.project_id.id),
            ("period", ">=", date(self.year, 1, 1)),
            ("period", "<=", date(self.year, 12, 1)),
        ])
        timesheet_by_key = {
            (timesheet.assignment_id.id, timesheet.period.month): timesheet
            for timesheet in existing_timesheets
        }

        for wizard_line in self.line_ids:
            for month in range(1, 13):
                value = wizard_line[f"month_{month:02d}"] or 0.0
                key = (wizard_line.assignment_id.id, month)
                timesheet = timesheet_by_key.get(key)
                period = date(self.year, month, 1)

                if not timesheet and abs(value) < 1e-9:
                    continue
                if not timesheet:
                    timesheet = Timesheet.create({
                        "assignment_id": wizard_line.assignment_id.id,
                        "period": period,
                    })
                    timesheet_by_key[key] = timesheet

                timesheet_line = timesheet.line_ids.filtered(
                    lambda line: line.hour_type == wizard_line.hour_type
                )[:1]
                if abs(value) < 1e-9:
                    if timesheet_line:
                        timesheet_line.unlink()
                    if not timesheet.line_ids:
                        timesheet.unlink()
                        timesheet_by_key.pop(key, None)
                    continue

                if timesheet_line:
                    timesheet_line.hours = value
                else:
                    Line.create({
                        "timesheet_id": timesheet.id,
                        "hour_type": wizard_line.hour_type,
                        "hours": value,
                    })

        return {"type": "ir.actions.act_window_close"}


class TenenetProjectTimesheetMatrixWizardLine(models.TransientModel):
    _name = "tenenet.project.timesheet.matrix.wizard.line"
    _description = "Riadok mesačnej matice timesheetu"
    _order = "employee_id, sequence, id"

    wizard_id = fields.Many2one(
        "tenenet.project.timesheet.matrix.wizard",
        string="Matica",
        required=True,
        ondelete="cascade",
    )
    assignment_id = fields.Many2one(
        "tenenet.project.assignment",
        string="Priradenie",
        required=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
    )
    hour_type = fields.Selection(
        [(meta["type"], meta["label"]) for meta in HOUR_FIELD_META.values()],
        string="Typ hodín",
        required=True,
    )
    name = fields.Char(string="Kategória", required=True)
    scope = fields.Selection(
        [("project", "Projektové hodiny"), ("leave", "Absencie")],
        string="Skupina",
        required=True,
    )
    sequence = fields.Integer(string="Poradie")
    month_01 = fields.Float(string=MONTH_LABELS[1], digits=(10, 2))
    month_02 = fields.Float(string=MONTH_LABELS[2], digits=(10, 2))
    month_03 = fields.Float(string=MONTH_LABELS[3], digits=(10, 2))
    month_04 = fields.Float(string=MONTH_LABELS[4], digits=(10, 2))
    month_05 = fields.Float(string=MONTH_LABELS[5], digits=(10, 2))
    month_06 = fields.Float(string=MONTH_LABELS[6], digits=(10, 2))
    month_07 = fields.Float(string=MONTH_LABELS[7], digits=(10, 2))
    month_08 = fields.Float(string=MONTH_LABELS[8], digits=(10, 2))
    month_09 = fields.Float(string=MONTH_LABELS[9], digits=(10, 2))
    month_10 = fields.Float(string=MONTH_LABELS[10], digits=(10, 2))
    month_11 = fields.Float(string=MONTH_LABELS[11], digits=(10, 2))
    month_12 = fields.Float(string=MONTH_LABELS[12], digits=(10, 2))
