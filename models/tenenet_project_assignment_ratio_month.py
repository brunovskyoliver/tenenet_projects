from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TenenetProjectAssignmentRatioMonth(models.Model):
    _name = "tenenet.project.assignment.ratio.month"
    _description = "Mesačný alokačný pomer priradenia"
    _order = "period"

    assignment_id = fields.Many2one(
        "tenenet.project.assignment",
        string="Priradenie",
        required=True,
        ondelete="cascade",
    )
    period = fields.Date(string="Obdobie", required=True)
    year = fields.Integer(string="Rok", compute="_compute_year_month", store=True)
    month = fields.Integer(string="Mesiac", compute="_compute_year_month", store=True)
    allocation_ratio = fields.Float(
        string="Úväzok na projekte (%)",
        digits=(5, 2),
        required=True,
        default=0.0,
    )

    _unique_assignment_period = models.Constraint(
        "UNIQUE(assignment_id, period)",
        "Pre priradenie môže existovať len jedna alokačná hodnota za mesiac.",
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

    @api.constrains("allocation_ratio")
    def _check_allocation_ratio(self):
        for rec in self:
            if rec.allocation_ratio < 0.0 or rec.allocation_ratio > 100.0:
                raise ValidationError("Mesačný úväzok musí byť v rozsahu 0 až 100 %.")

    @api.model_create_multi
    def create(self, vals_list):
        normalized_vals_list = []
        for vals in vals_list:
            normalized_vals = dict(vals)
            if normalized_vals.get("period"):
                normalized_vals["period"] = self._normalize_period(normalized_vals["period"])
            normalized_vals_list.append(normalized_vals)
        records = super().create(normalized_vals_list)
        records.mapped("assignment_id")._after_ratio_plan_changed(set(records.mapped("period")))
        return records

    def write(self, vals):
        assignments = self.mapped("assignment_id")
        periods = set(self.mapped("period"))
        vals = dict(vals)
        if vals.get("period"):
            vals["period"] = self._normalize_period(vals["period"])
        result = super().write(vals)
        assignments |= self.mapped("assignment_id")
        periods |= set(self.mapped("period"))
        assignments._after_ratio_plan_changed(periods)
        return result

    def unlink(self):
        assignments = self.mapped("assignment_id")
        periods = set(self.mapped("period"))
        result = super().unlink()
        assignments._after_ratio_plan_changed(periods)
        return result
