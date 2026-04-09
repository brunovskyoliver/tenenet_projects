from datetime import date

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TenenetProjectBudgetLineMonth(models.Model):
    _name = "tenenet.project.budget.line.month"
    _description = "Mesačný plán rozpočtovej položky"
    _order = "period"

    budget_line_id = fields.Many2one(
        "tenenet.project.budget.line",
        string="Rozpočtová položka",
        required=True,
        ondelete="cascade",
    )
    period = fields.Date(string="Obdobie", required=True)
    year = fields.Integer(string="Rok", compute="_compute_year_month", store=True)
    month = fields.Integer(string="Mesiac", compute="_compute_year_month", store=True)
    amount = fields.Monetary(string="Suma", currency_field="currency_id", required=True, default=0.0)
    currency_id = fields.Many2one(
        "res.currency",
        related="budget_line_id.currency_id",
        store=True,
        readonly=True,
    )

    _unique_budget_line_period = models.Constraint(
        "UNIQUE(budget_line_id, period)",
        "Pre rozpočtovú položku môže existovať len jedna hodnota za mesiac.",
    )

    @api.depends("period")
    def _compute_year_month(self):
        for rec in self:
            if rec.period:
                rec.year = rec.period.year
                rec.month = rec.period.month
            else:
                rec.year = 0
                rec.month = 0

    @api.model
    def _normalize_period(self, value):
        period = fields.Date.to_date(value)
        return period.replace(day=1) if period else False

    @api.constrains("amount")
    def _check_non_negative_amount(self):
        for rec in self:
            if rec.amount < 0.0:
                raise ValidationError("Mesačná suma rozpočtovej položky nemôže byť záporná.")

    @api.constrains("budget_line_id", "period")
    def _check_period_matches_budget_line_year(self):
        for rec in self:
            if rec.budget_line_id and rec.period and rec.period.year != rec.budget_line_id.year:
                raise ValidationError("Mesačný plán musí zostať v roku rozpočtovej položky.")

    @api.model_create_multi
    def create(self, vals_list):
        normalized_vals_list = []
        for vals in vals_list:
            normalized_vals = dict(vals)
            if normalized_vals.get("period"):
                normalized_vals["period"] = self._normalize_period(normalized_vals["period"])
            normalized_vals_list.append(normalized_vals)
        return super().create(normalized_vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get("period"):
            vals["period"] = self._normalize_period(vals["period"])
        return super().write(vals)
