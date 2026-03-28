from odoo import api, fields, models


class TenenetProjectExpense(models.Model):
    _name = "tenenet.project.expense"
    _description = "Projektový výdavok"
    _order = "date desc, project_id"
    _rec_name = "description"

    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
    )
    allowed_type_id = fields.Many2one(
        "tenenet.project.allowed.expense.type",
        string="Typ výdavku",
        required=True,
        ondelete="restrict",
        domain="[('project_id', '=', project_id)]",
    )
    date = fields.Date(
        string="Dátum",
        required=True,
        default=fields.Date.today,
    )
    amount = fields.Monetary(
        string="Suma",
        currency_field="currency_id",
        required=True,
    )
    description = fields.Char(string="Popis", required=True)
    note = fields.Text(string="Poznámka")
    currency_id = fields.Many2one(
        "res.currency",
        related="project_id.currency_id",
        store=True,
    )
    charged_to = fields.Selection(
        [
            ("project", "Projekt"),
            ("internal", "Interné"),
        ],
        string="Účtuje sa na",
        required=True,
        default="project",
        help="Projekt: hradené z projektového rozpočtu. Interné: hradené z interných zdrojov TENENET.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "charged_to" not in vals or vals.get("charged_to") == "project":
                vals["charged_to"] = self._compute_charged_to(vals)
        return super().create(vals_list)

    def write(self, vals):
        # Re-evaluate charged_to when amount or type changes, unless explicitly set.
        if ("amount" in vals or "allowed_type_id" in vals) and "charged_to" not in vals:
            for rec in self:
                check_vals = dict(vals)
                check_vals.setdefault("amount", rec.amount)
                check_vals.setdefault("allowed_type_id", rec.allowed_type_id.id)
                check_vals.setdefault("project_id", rec.project_id.id)
                vals["charged_to"] = self._compute_charged_to(check_vals, exclude_id=rec.id)
                break
        return super().write(vals)

    def _compute_charged_to(self, vals, exclude_id=None):
        """Return 'project' or 'internal' based on whether the type's budget allows it."""
        allowed_type_id = vals.get("allowed_type_id")
        if not allowed_type_id:
            return "project"
        expense_type = self.env["tenenet.project.allowed.expense.type"].browse(allowed_type_id)
        if not expense_type.exists() or not expense_type.max_amount:
            return "project"
        domain = [
            ("allowed_type_id", "=", expense_type.id),
            ("charged_to", "=", "project"),
        ]
        if exclude_id:
            domain.append(("id", "!=", exclude_id))
        already_spent = sum(
            self.search(domain).mapped("amount")
        )
        return "project" if already_spent < expense_type.max_amount else "internal"
