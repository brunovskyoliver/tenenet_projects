from odoo import api, fields, models


class TenenetCompanyExpense(models.Model):
    _name = "tenenet.company.expense"
    _description = "Náklady Tenenet – nepridelené na projekty"
    _order = "period desc, employee_id, expense_type"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Zamestnanec",
        required=True,
        ondelete="cascade",
    )
    period = fields.Date(
        string="Obdobie",
        required=True,
        help="Prvý deň mesiaca",
    )
    expense_type = fields.Selection(
        [
            ("vacation", "Dovolenka"),
            ("sick", "PN/OČR"),
            ("doctor", "Lekár"),
            ("holidays", "Sviatky"),
        ],
        string="Typ nákladu",
        required=True,
    )
    leave_id = fields.Many2one(
        "hr.leave",
        string="Dovolenka",
        ondelete="set null",
        help="Odkaz na pôvodnú dovolenku z hr_holidays",
    )
    hours = fields.Float(
        string="Hodiny",
        digits=(10, 2),
        default=0.0,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
    )
    hourly_rate_hm = fields.Float(
        string="Hodinová sadzba HM",
        digits=(10, 4),
        help="Priemerná hodinová hrubá mzda zamestnanca",
    )
    hourly_rate_ccp = fields.Float(
        string="Hodinová sadzba CCP",
        digits=(10, 4),
        help="Priemerná hodinová celková cena práce zamestnanca",
    )
    cost_hm = fields.Monetary(
        string="Náklad HM",
        currency_field="currency_id",
        compute="_compute_costs",
        store=True,
    )
    cost_ccp = fields.Monetary(
        string="Náklad CCP",
        currency_field="currency_id",
        compute="_compute_costs",
        store=True,
    )
    note = fields.Text(
        string="Poznámka",
        help="Dôvod prečo náklad nie je pridelený na projekt",
    )

    _unique_employee_period_type_leave = models.Constraint(
        "UNIQUE(employee_id, period, expense_type, leave_id)",
        "Pre zamestnanca môže existovať len jeden záznam pre daný typ a dovolenku za obdobie.",
    )

    @api.depends("hours", "hourly_rate_hm", "hourly_rate_ccp")
    def _compute_costs(self):
        for rec in self:
            rec.cost_hm = (rec.hours or 0.0) * (rec.hourly_rate_hm or 0.0)
            rec.cost_ccp = (rec.hours or 0.0) * (rec.hourly_rate_ccp or 0.0)

    @api.model
    def _get_employee_average_rates(self, employee, period):
        """Get average hourly rates for an employee from their assignments."""
        assignments = self.env["tenenet.project.assignment"].search([
            ("employee_id", "=", employee.id),
            ("active", "=", True),
        ])
        if not assignments:
            return 0.0, 0.0

        total_hm = sum(a.wage_hm or 0.0 for a in assignments)
        total_ccp = sum(a.wage_ccp or 0.0 for a in assignments)
        count = len(assignments)
        return total_hm / count, total_ccp / count

    @api.model
    def _create_or_update_expense(self, employee, period, expense_type, hours, leave=None, note=None):
        """Create or update a company expense record."""
        period_normalized = period.replace(day=1)
        domain = [
            ("employee_id", "=", employee.id),
            ("period", "=", period_normalized),
            ("expense_type", "=", expense_type),
        ]
        if leave:
            domain.append(("leave_id", "=", leave.id))

        existing = self.search(domain, limit=1)
        avg_hm, avg_ccp = self._get_employee_average_rates(employee, period_normalized)

        vals = {
            "hours": hours,
            "hourly_rate_hm": avg_hm,
            "hourly_rate_ccp": avg_ccp,
        }
        if note:
            vals["note"] = note

        if existing:
            existing.write(vals)
            return existing
        else:
            vals.update({
                "employee_id": employee.id,
                "period": period_normalized,
                "expense_type": expense_type,
                "leave_id": leave.id if leave else False,
            })
            return self.create(vals)


class TenenetCompanyExpenseSummary(models.Model):
    _name = "tenenet.company.expense.summary"
    _description = "Súhrn nákladov Tenenet za obdobie"
    _auto = False
    _order = "period desc, expense_type"

    period = fields.Date(string="Obdobie", readonly=True)
    expense_type = fields.Selection(
        [
            ("vacation", "Dovolenka"),
            ("sick", "PN/OČR"),
            ("doctor", "Lekár"),
            ("holidays", "Sviatky"),
        ],
        string="Typ nákladu",
        readonly=True,
    )
    employee_count = fields.Integer(string="Počet zamestnancov", readonly=True)
    total_hours = fields.Float(string="Hodiny spolu", digits=(10, 2), readonly=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
    )
    total_cost_hm = fields.Monetary(
        string="Náklad HM spolu",
        currency_field="currency_id",
        readonly=True,
    )
    total_cost_ccp = fields.Monetary(
        string="Náklad CCP spolu",
        currency_field="currency_id",
        readonly=True,
    )

    def init(self):
        self.env.cr.execute("""
            DROP VIEW IF EXISTS tenenet_company_expense_summary;
            CREATE OR REPLACE VIEW tenenet_company_expense_summary AS (
                SELECT
                    ROW_NUMBER() OVER () AS id,
                    e.period,
                    e.expense_type,
                    COUNT(DISTINCT e.employee_id) AS employee_count,
                    SUM(e.hours) AS total_hours,
                    (SELECT id FROM res_currency WHERE name = 'EUR' LIMIT 1) AS currency_id,
                    SUM(e.cost_hm) AS total_cost_hm,
                    SUM(e.cost_ccp) AS total_cost_ccp
                FROM tenenet_company_expense e
                GROUP BY e.period, e.expense_type
            )
        """)
