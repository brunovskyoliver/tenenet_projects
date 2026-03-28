from odoo import api, fields, models


class TenenetProjectAllowedExpenseType(models.Model):
    _name = "tenenet.project.allowed.expense.type"
    _description = "Povolený typ výdavku projektu"
    _order = "project_id, name"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(string="Typ výdavku", required=True)
    description = fields.Text(string="Popis")
    currency_id = fields.Many2one(
        "res.currency",
        related="project_id.currency_id",
        store=True,
    )
    max_amount = fields.Monetary(
        string="Max. povolená suma",
        currency_field="currency_id",
        default=0.0,
        help="Maximálna suma výdavkov tohto typu na projekte. 0 = bez limitu.",
    )
    expense_ids = fields.One2many(
        "tenenet.project.expense",
        "allowed_type_id",
        string="Výdavky",
    )
    total_project_spent = fields.Monetary(
        string="Vyčerpané (projekt)",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    total_internal_spent = fields.Monetary(
        string="Interné výdavky",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    remaining = fields.Monetary(
        string="Zostatok",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
        help="Zostatok do limitu. Prázdne ak limit nie je nastavený.",
    )

    @api.depends("max_amount", "expense_ids.amount", "expense_ids.charged_to")
    def _compute_totals(self):
        for rec in self:
            project_expenses = rec.expense_ids.filtered(lambda e: e.charged_to == "project")
            internal_expenses = rec.expense_ids.filtered(lambda e: e.charged_to == "internal")
            rec.total_project_spent = sum(project_expenses.mapped("amount"))
            rec.total_internal_spent = sum(internal_expenses.mapped("amount"))
            if rec.max_amount:
                rec.remaining = max(0.0, rec.max_amount - rec.total_project_spent)
            else:
                rec.remaining = 0.0
