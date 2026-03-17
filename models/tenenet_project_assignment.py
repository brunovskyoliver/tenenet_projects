from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TenenetProjectAssignment(models.Model):
    _name = "tenenet.project.assignment"
    _description = "Priradenie zamestnanca k projektu"
    _order = "project_id, employee_id"

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

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_start > rec.date_end:
                raise ValidationError(
                    "Dátum začiatku priradenia nemôže byť po dátume konca."
                )
