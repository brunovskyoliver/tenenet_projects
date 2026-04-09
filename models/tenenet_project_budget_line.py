from datetime import date

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class TenenetProjectBudgetLine(models.Model):
    _name = "tenenet.project.budget.line"
    _description = "Rozpočtová položka projektu"
    _order = "year desc, budget_type, sequence, id"

    name = fields.Char(string="Názov položky", required=True)
    sequence = fields.Integer(string="Poradie", default=10)
    project_id = fields.Many2one(
        "tenenet.project",
        string="Projekt",
        required=True,
        ondelete="cascade",
    )
    year = fields.Integer(
        string="Rok",
        required=True,
        default=lambda self: fields.Date.context_today(self).year,
    )
    budget_type = fields.Selection(
        [
            ("pausal", "Paušálne"),
            ("labor", "Mzdové"),
            ("other", "Iné"),
        ],
        string="Typ rozpočtu",
        required=True,
        default="labor",
    )
    program_id = fields.Many2one(
        "tenenet.program",
        string="Program",
        required=True,
        ondelete="restrict",
    )
    amount = fields.Monetary(
        string="Suma",
        currency_field="currency_id",
        required=True,
        default=0.0,
    )
    note = fields.Text(string="Poznámka")
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        related="project_id.currency_id",
        store=True,
        readonly=True,
    )
    budget_month_ids = fields.One2many(
        "tenenet.project.budget.line.month",
        "budget_line_id",
        string="Mesačný plán",
    )
    has_explicit_month_plan = fields.Boolean(
        string="Má explicitný mesačný plán",
        default=False,
    )
    planner_state = fields.Json(
        string="P&L planner",
        compute="_compute_planner_state",
    )

    @api.depends("year")
    def _compute_planner_state(self):
        for rec in self:
            rec.planner_state = {"current_year": rec.year or fields.Date.context_today(self).year}

    @api.model
    def _get_admin_tenenet_program(self):
        return self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1)

    @api.constrains("amount")
    def _check_non_negative_amount(self):
        for rec in self:
            if rec.amount < 0.0:
                raise ValidationError("Rozpočtová položka nemôže mať zápornú sumu.")

    @api.constrains("project_id", "program_id", "budget_type")
    def _check_program_belongs_to_project(self):
        admin_program = self._get_admin_tenenet_program()
        for rec in self:
            if not rec.project_id or not rec.program_id:
                continue
            if rec.budget_type == "pausal":
                if rec.program_id != admin_program:
                    raise ValidationError("Paušálna rozpočtová položka musí byť vždy v programe Admin TENENET.")
                continue
            if rec.project_id.is_tenenet_internal:
                if rec.program_id.code != "ADMIN_TENENET":
                    raise ValidationError("Interný projekt môže používať iba program Admin TENENET.")
                continue
            if rec.program_id not in rec.project_id.program_ids:
                raise ValidationError("Program rozpočtovej položky musí patriť medzi programy projektu.")

    @api.constrains("budget_month_ids", "amount")
    def _check_month_plan_total(self):
        for rec in self:
            if not rec.has_explicit_month_plan:
                continue
            total = sum(rec.budget_month_ids.mapped("amount"))
            if float_compare(total, rec.amount, precision_rounding=rec.currency_id.rounding) > 0:
                raise ValidationError("Súčet mesačných hodnôt nemôže byť vyšší ako celá suma rozpočtovej položky.")

    def _get_explicit_month_amounts(self):
        self.ensure_one()
        months = {month: 0.0 for month in range(1, 13)}
        for line in self.budget_month_ids.sorted("period"):
            months[line.month] = line.amount or 0.0
        return months

    def _get_effective_month_amounts(self):
        self.ensure_one()
        if self.has_explicit_month_plan:
            return self._get_explicit_month_amounts()
        return self.project_id._allocate_annual_amount_by_project_plan(self.year, self.amount)

    def _replace_month_amounts(self, normalized_amounts):
        self.ensure_one()
        self.budget_month_ids.unlink()
        values_list = []
        for month in sorted(normalized_amounts):
            if abs(normalized_amounts[month]) < 0.00001:
                continue
            values_list.append({
                "budget_line_id": self.id,
                "period": date(self.year, month, 1),
                "amount": normalized_amounts[month],
            })
        if values_list:
            self.env["tenenet.project.budget.line.month"].create(values_list)
        self.write({"has_explicit_month_plan": True})
        return True

    def set_month_amounts(self, month_amounts):
        self.ensure_one()
        if not isinstance(month_amounts, dict):
            raise ValidationError("Mesačné rozdelenie musí byť zadané ako mapa mesiacov.")

        currency = self.currency_id or self.env.company.currency_id
        normalized_amounts = {}
        for month_key, amount in month_amounts.items():
            month = int(month_key)
            if month < 1 or month > 12:
                raise ValidationError("Mesiace plánu musia byť v rozsahu 1 až 12.")
            amount_value = currency.round(float(amount or 0.0))
            if amount_value < 0:
                raise ValidationError("Mesačná suma plánu nemôže byť záporná.")
            normalized_amounts[month] = amount_value

        total_amount = sum(normalized_amounts.values())
        if float_compare(total_amount, self.amount, precision_rounding=currency.rounding) > 0:
            raise ValidationError("Súčet mesačných hodnôt nemôže byť vyšší ako celá suma rozpočtovej položky.")

        return self._replace_month_amounts(normalized_amounts)

    def get_planner_data(self):
        self.ensure_one()
        month_values = self._get_effective_month_amounts()
        active_months = [month for month, amount in month_values.items() if abs(amount) > 0.00001]
        return {
            "budget_line_id": self.id,
            "project_id": self.project_id.id,
            "project_name": self.project_id.display_name,
            "year": self.year,
            "amount": self.amount,
            "name": self.name,
            "label": f"{self.project_id.display_name} / {self.name}",
            "budget_type": self.budget_type,
            "budget_type_label": dict(self._fields["budget_type"].selection).get(self.budget_type, ""),
            "program_id": self.program_id.id,
            "program_label": self.program_id.display_name or "",
            "note": self.note or "",
            "months": {str(month): month_values.get(month, 0.0) for month in range(1, 13)},
            "start_month": active_months[0] if active_months else False,
            "end_month": active_months[-1] if active_months else False,
            "has_explicit_month_plan": bool(self.has_explicit_month_plan),
            "currency_symbol": self.currency_id.symbol or "",
            "currency_position": self.currency_id.position or "after",
        }

    def action_open_planner(self):
        self.ensure_one()
        return {
            "name": "P&L planner",
            "type": "ir.actions.client",
            "tag": "tenenet_budget_line_planner_action",
            "target": "new",
            "params": {
                "budget_line_id": self.id,
            },
            "context": dict(self.env.context, dialog_size="extra-large"),
        }
