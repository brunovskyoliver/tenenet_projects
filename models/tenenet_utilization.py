from odoo import api, fields, models


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
    manager_name = fields.Char(string="Manažér")
    period = fields.Date(string="Obdobie", required=True)

    work_ratio = fields.Float(string="Úväzok (%)", digits=(5, 2))
    capacity_hours = fields.Float(string="Kapacita hodín", digits=(10, 2))

    hours_pp = fields.Float(string="Hodiny PP", digits=(10, 2))
    hours_np = fields.Float(string="Hodiny NP", digits=(10, 2))
    hours_travel = fields.Float(string="Hodiny cesta za klientom", digits=(10, 2))
    hours_training = fields.Float(string="Hodiny školenie", digits=(10, 2))
    hours_ambulance = fields.Float(string="Hodiny ambulancia", digits=(10, 2))
    hours_international = fields.Float(string="Hodiny medzinárodné projekty", digits=(10, 2))
    hours_project_total = fields.Float(
        string="Projektové hodiny spolu",
        digits=(10, 2),
        compute="_compute_hours_project_total",
        store=True,
    )

    hours_vacation = fields.Float(string="Hodiny dovolenka", digits=(10, 2))
    hours_doctor = fields.Float(string="Hodiny lekár", digits=(10, 2))
    hours_sick = fields.Float(string="Hodiny PN/OČR", digits=(10, 2))
    hours_ballast = fields.Float(string="Hodiny balast", digits=(10, 2))
    hours_non_project_total = fields.Float(
        string="Neprojektové hodiny spolu",
        digits=(10, 2),
        compute="_compute_hours_non_project_total",
        store=True,
    )

    utilization_rate = fields.Float(
        string="Miera vyťaženosti",
        digits=(6, 4),
        compute="_compute_utilization_rate",
        store=True,
    )
    utilization_status = fields.Selection(
        [("ok", "OK"), ("warning", "!")],
        string="Stav vyťaženosti",
        compute="_compute_utilization_status",
        store=True,
    )
    non_project_rate = fields.Float(
        string="Miera neprojektových hodín",
        digits=(6, 4),
        compute="_compute_non_project_rate",
        store=True,
    )
    non_project_status = fields.Selection(
        [("ok", "OK"), ("warning", "!")],
        string="Stav neprojektových hodín",
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

    @api.depends("hours_vacation", "hours_doctor", "hours_sick", "hours_ballast")
    def _compute_hours_non_project_total(self):
        for rec in self:
            rec.hours_non_project_total = (
                (rec.hours_vacation or 0.0)
                + (rec.hours_doctor or 0.0)
                + (rec.hours_sick or 0.0)
                + (rec.hours_ballast or 0.0)
            )

    @api.depends("hours_project_total", "capacity_hours")
    def _compute_utilization_rate(self):
        for rec in self:
            rec.utilization_rate = (
                (rec.hours_project_total / rec.capacity_hours) if rec.capacity_hours else 0.0
            )

    @api.depends("utilization_rate")
    def _compute_utilization_status(self):
        for rec in self:
            rec.utilization_status = "ok" if rec.utilization_rate >= 0.8 else "warning"

    @api.depends("hours_non_project_total", "capacity_hours")
    def _compute_non_project_rate(self):
        for rec in self:
            rec.non_project_rate = (
                (rec.hours_non_project_total / rec.capacity_hours) if rec.capacity_hours else 0.0
            )

    @api.depends("non_project_rate")
    def _compute_non_project_status(self):
        for rec in self:
            rec.non_project_status = "ok" if rec.non_project_rate <= 0.25 else "warning"

    @api.depends("hours_project_total", "hours_non_project_total", "capacity_hours")
    def _compute_hours_diff(self):
        for rec in self:
            rec.hours_diff = (
                (rec.hours_project_total or 0.0)
                + (rec.hours_non_project_total or 0.0)
                - (rec.capacity_hours or 0.0)
            )
