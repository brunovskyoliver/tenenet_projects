from odoo import api, fields, models


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

    # ── Projektové hodiny ────────────────────────────────────────────────────
    hours_pp = fields.Float(string="Hodiny PP (priama práca)", digits=(10, 2))
    hours_np = fields.Float(string="Hodiny NP (nepriama práca)", digits=(10, 2))
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

    # ── Absencie ─────────────────────────────────────────────────────────────
    hours_vacation = fields.Float(string="Hodiny dovolenka", digits=(10, 2))
    hours_sick = fields.Float(string="Hodiny PN/OČR", digits=(10, 2))
    hours_doctor = fields.Float(string="Hodiny lekár", digits=(10, 2))
    hours_holidays = fields.Float(string="Hodiny platené sviatky", digits=(10, 2))
    hours_leave_total = fields.Float(
        string="Absencie spolu",
        digits=(10, 2),
        compute="_compute_hours_leave_total",
        store=True,
    )
    leave_auto_synced = fields.Boolean(
        string="Absencie sync. z hr_holidays",
        default=False,
        help="Označuje, že hodiny absencií boli automaticky synchronizované z Odoo dovoleniek.",
    )

    # ── Celkové hodiny ───────────────────────────────────────────────────────
    hours_total = fields.Float(
        string="Hodiny spolu",
        digits=(10, 2),
        compute="_compute_hours_total",
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

    @api.depends(
        "hours_pp", "hours_np", "hours_travel",
        "hours_training", "hours_ambulance", "hours_international",
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

    @api.depends("hours_vacation", "hours_sick", "hours_doctor", "hours_holidays")
    def _compute_hours_leave_total(self):
        for rec in self:
            rec.hours_leave_total = (
                (rec.hours_vacation or 0.0)
                + (rec.hours_sick or 0.0)
                + (rec.hours_doctor or 0.0)
                + (rec.hours_holidays or 0.0)
            )

    @api.depends("hours_project_total", "hours_leave_total")
    def _compute_hours_total(self):
        for rec in self:
            rec.hours_total = (rec.hours_project_total or 0.0) + (rec.hours_leave_total or 0.0)

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
