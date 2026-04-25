import logging
from datetime import date

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

INTERNAL_EXPENSE_CATEGORY = [
    ("leave", "Dovolenka"),
    ("wage", "Mzda"),
    ("residual_wage", "Dorovnanie mzdy"),
    ("expense", "Výdavok"),
]

LEAVE_HOUR_TYPE = [
    ("vacation", "Dovolenka"),
    ("sick", "PN/OČR"),
    ("doctor", "Lekár"),
    ("holidays", "Sviatky"),
]


class TenenetInternalExpense(models.Model):
    _name = "tenenet.internal.expense"
    _description = "Interný náklad TENENET"
    _order = "period desc, employee_id, category"
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
    period = fields.Date(
        string="Obdobie",
        required=True,
        help="Prvý deň mesiaca, ku ktorému sa náklad vzťahuje.",
    )
    category = fields.Selection(
        INTERNAL_EXPENSE_CATEGORY,
        string="Kategória",
        required=True,
    )
    leave_id = fields.Many2one(
        "hr.leave",
        string="Dovolenka",
        ondelete="set null",
        help="Zdrojová žiadosť o dovolenku (len pre kategóriu Dovolenka).",
    )
    hr_expense_id = fields.Many2one(
        "hr.expense",
        string="Zdrojový výdavok",
        ondelete="cascade",
        index=True,
        help="Pôvodný záznam z hr.expense pri projektových výdavkoch presunutých na interné náklady.",
    )
    source_project_id = fields.Many2one(
        "tenenet.project",
        string="Zdrojový projekt",
        ondelete="set null",
        help="Projekt, z ktorého išla nepokrytá časť výdavku do interných nákladov.",
    )
    expense_type_config_id = fields.Many2one(
        "tenenet.expense.type.config",
        string="Typ nákladu (katalóg)",
        ondelete="set null",
    )
    source_assignment_id = fields.Many2one(
        "tenenet.project.assignment",
        string="Zdrojové priradenie",
        ondelete="set null",
        help="Priradenie, ku ktorému mal byť náklad priradený, ale nemohol byť (z dôvodu limitu alebo stropu).",
    )
    tenenet_cost_id = fields.Many2one(
        "tenenet.employee.tenenet.cost",
        string="Zdrojové mesačné dorovnanie",
        ondelete="cascade",
        index=True,
        help="Technický odkaz na mesačný prepočet dorovnania hrubej mzdy.",
    )
    hour_type = fields.Selection(
        LEAVE_HOUR_TYPE,
        string="Typ hodín",
        help="Typ hodín dovolenky (len pre kategóriu Dovolenka).",
    )
    hours = fields.Float(
        string="Hodiny",
        digits=(10, 2),
        default=0.0,
        help="Počet hodín (len pre kategóriu Dovolenka).",
    )
    wage_hm = fields.Float(
        string="Hodinová mzda HM (brutto)",
        digits=(10, 4),
        help="Hodinová brutto mzda prevzatá zo zdrojového priradenia.",
    )
    wage_ccp = fields.Float(
        string="Hodinová sadzba CCP",
        digits=(10, 4),
        compute="_compute_wage_ccp",
        store=True,
        help="Celková cena práce za hodinu = mzda HM × 1.362",
    )
    cost_hm = fields.Monetary(
        string="Náklad HM (brutto)",
        currency_field="currency_id",
        compute="_compute_costs",
        store=True,
        readonly=False,
        help="Pre dovolenku: hodiny × mzda HM. Pre mzdu: HM/brutto odvodené z CCP alebo priamy prebytok nad stropom.",
    )
    expense_amount = fields.Monetary(
        string="Suma výdavku",
        currency_field="currency_id",
        help="Pri kategórii Výdavok ide o internú časť sumy z hr.expense.",
    )
    cost_ccp = fields.Monetary(
        string="Náklad CCP",
        currency_field="currency_id",
        compute="_compute_cost_ccp",
        store=True,
        readonly=True,
        help="Náklad CCP = Náklad HM × 1.362",
    )
    note = fields.Text(string="Poznámka")
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
    )

    # Unique constraints — PostgreSQL NULLs are not equal in UNIQUE so
    # leave_id=NULL wage records never conflict with leave rows.
    _unique_leave = models.Constraint(
        "UNIQUE(leave_id, period, employee_id)",
        "Pre dovolenku môže existovať len jeden interný náklad za zamestnanca a obdobie.",
    )
    _unique_wage = models.Constraint(
        "UNIQUE(source_assignment_id, period, category)",
        "Pre priradenie môže existovať len jeden mzdový náklad za obdobie.",
    )
    _unique_hr_expense = models.Constraint(
        "UNIQUE(hr_expense_id)",
        "Pre jeden HR výdavok môže existovať len jeden interný náklad typu výdavok.",
    )
    _unique_tenenet_cost = models.Constraint(
        "UNIQUE(tenenet_cost_id)",
        "Pre jedno mesačné dorovnanie môže existovať len jeden interný náklad.",
    )

    @api.depends("employee_id", "period", "category")
    def _compute_name(self):
        category_labels = dict(INTERNAL_EXPENSE_CATEGORY)
        for rec in self:
            emp = rec.employee_id.display_name or ""
            period_str = rec.period.strftime("%m/%Y") if rec.period else ""
            cat_str = category_labels.get(rec.category, rec.category or "")
            rec.name = f"{emp} / {period_str} / {cat_str}"

    CCP_MULTIPLIER = 1.362

    def _get_ccp_multiplier(self):
        self.ensure_one()
        employee = self.source_assignment_id.employee_id or self.employee_id
        if employee and hasattr(employee, "_get_payroll_contribution_multiplier"):
            return employee._get_payroll_contribution_multiplier()
        return self.CCP_MULTIPLIER

    @api.depends("wage_hm", "employee_id.tenenet_payroll_contribution_multiplier", "source_assignment_id.employee_id.tenenet_payroll_contribution_multiplier")
    def _compute_wage_ccp(self):
        for rec in self:
            rec.wage_ccp = (rec.wage_hm or 0.0) * rec._get_ccp_multiplier()

    @api.depends("hours", "wage_hm", "category")
    def _compute_costs(self):
        for rec in self:
            if rec.category == "leave":
                rec.cost_hm = (rec.hours or 0.0) * (rec.wage_hm or 0.0)
            elif rec.category == "expense":
                rec.cost_hm = rec.expense_amount or 0.0
            # For "wage" category, cost_hm is written directly by _check_wage_cap().

    @api.depends("cost_hm", "expense_amount", "category", "employee_id.tenenet_payroll_contribution_multiplier", "source_assignment_id.employee_id.tenenet_payroll_contribution_multiplier")
    def _compute_cost_ccp(self):
        for rec in self:
            if rec.category == "expense":
                rec.cost_ccp = rec.expense_amount or 0.0
            else:
                rec.cost_ccp = (rec.cost_hm or 0.0) * rec._get_ccp_multiplier()

    @api.onchange("source_assignment_id")
    def _onchange_source_assignment_id(self):
        if self.source_assignment_id:
            self.wage_hm = self.source_assignment_id.wage_hm

    @api.model
    def cleanup_orphaned_project_expenses(self):
        """Remove stale internal expenses left after deleted project/assignment records."""
        orphaned = self.search([
            ("category", "in", ["wage", "expense", "leave"]),
            ("source_project_id", "=", False),
            ("source_assignment_id", "=", False),
            ("tenenet_cost_id", "=", False),
            ("hr_expense_id", "=", False),
            ("leave_id", "=", False),
        ])
        if orphaned:
            orphaned.unlink()
        return len(orphaned)
