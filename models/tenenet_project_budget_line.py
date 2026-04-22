from datetime import date

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class TenenetProjectBudgetLine(models.Model):
    _name = "tenenet.project.budget.line"
    _description = "Rozpočtová položka projektu"
    _order = "year desc, budget_type, sequence, id"
    SERVICE_INCOME_SELECTION = [
        ("sales_individual", "Tržby individuálne"),
        ("sales_invoice", "Tržby fakturačné"),
        ("fundraising_individual", "Zbierky individuálne"),
        ("fundraising_corporate", "Zbierky korporátne"),
    ]

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
    expense_type_config_id = fields.Many2one(
        "tenenet.expense.type.config",
        string="Kategória výdavku",
        ondelete="restrict",
    )
    service_income_type = fields.Selection(
        SERVICE_INCOME_SELECTION,
        string="Typ servisného príjmu",
    )
    can_cover_payroll = fields.Boolean(
        string="Môže kryť mzdy",
        default=False,
    )
    payroll_employee_ids = fields.Many2many(
        "hr.employee",
        "tenenet_project_budget_line_payroll_employee_rel",
        "budget_line_id",
        "employee_id",
        string="Povolení zamestnanci pre mzdy",
        help="Ak je zoznam prázdny, položku môžu používať všetci aktuálne priradení zamestnanci projektu. Inak len vybraní zamestnanci s aktívnym priradením v danom mesiaci.",
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
    detail_label = fields.Char(
        string="Detail",
        compute="_compute_detail_label",
    )

    @api.depends("year")
    def _compute_planner_state(self):
        for rec in self:
            rec.planner_state = {"current_year": rec.year or fields.Date.context_today(self).year}

    @api.depends("name", "expense_type_config_id", "service_income_type")
    def _compute_detail_label(self):
        for rec in self:
            rec.detail_label = rec._get_detail_label()

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
            if rec.project_id.is_tenenet_internal or rec.project_id.project_type == "medzinarodny":
                if rec.program_id.code != "ADMIN_TENENET":
                    raise ValidationError("Interný alebo medzinárodný projekt môže používať iba program Admin TENENET.")
                continue
            if rec.program_id not in rec.project_id.program_ids:
                raise ValidationError("Program rozpočtovej položky musí patriť medzi programy projektu.")

    @api.constrains(
        "budget_type",
        "expense_type_config_id",
        "service_income_type",
        "can_cover_payroll",
        "project_id",
        "payroll_employee_ids",
    )
    def _check_budget_line_detail_rules(self):
        for rec in self:
            if rec.budget_type != "other":
                if rec.expense_type_config_id or rec.service_income_type or rec.can_cover_payroll or rec.payroll_employee_ids:
                    raise ValidationError("Doplňujúce nastavenia sú dostupné iba pre rozpočtový typ Iné.")
                continue
            if rec.service_income_type:
                if rec.expense_type_config_id:
                    raise ValidationError("Servisný príjem nemôže mať zároveň kategóriu výdavku.")
                if rec.project_id and rec.project_id.project_type != "sluzby":
                    raise ValidationError("Servisné príjmy možno použiť iba pri projekte typu Služby.")
            elif not rec.expense_type_config_id:
                raise ValidationError("Pri položke Iné treba zvoliť kategóriu výdavku alebo servisný príjem.")
            if rec.can_cover_payroll and not rec.service_income_type:
                raise ValidationError("Mzdy možno kryť iba pri servisných príjmoch.")
            if rec.payroll_employee_ids and not (rec.service_income_type == "sales_individual" and rec.can_cover_payroll):
                raise ValidationError("Výber zamestnancov pre mzdy je dostupný iba pri Tržbách individuálne s povoleným krytím miezd.")
            invalid_employees = rec.payroll_employee_ids.filtered(
                lambda employee: employee not in rec.project_id.assignment_ids.mapped("employee_id")
            )
            if invalid_employees:
                raise ValidationError("Vybraní zamestnanci pre mzdy musia byť priradení k rovnakému projektu.")

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

    def _get_detail_label(self):
        self.ensure_one()
        if self.service_income_type:
            return dict(self._fields["service_income_type"].selection).get(self.service_income_type, self.name)
        if self.expense_type_config_id:
            return self.expense_type_config_id.display_name or self.name
        return self.name

    def _normalize_detail_values(self, vals):
        values = dict(vals)
        current_record = self[:1]
        budget_type = values.get("budget_type") or current_record.budget_type
        current_expense_type_id = current_record.expense_type_config_id.id if current_record else False
        current_service_income_type = current_record.service_income_type if current_record else False
        current_can_cover_payroll = current_record.can_cover_payroll if current_record else False
        current_payroll_employee_ids = current_record.payroll_employee_ids.ids if current_record else []
        expense_type_config_id = (
            values.get("expense_type_config_id")
            if "expense_type_config_id" in values
            else current_expense_type_id
        )
        service_income_type = (
            values.get("service_income_type")
            if "service_income_type" in values
            else current_service_income_type
        )
        can_cover_payroll = (
            values.get("can_cover_payroll")
            if "can_cover_payroll" in values
            else current_can_cover_payroll
        )
        payroll_employee_ids = values.get("payroll_employee_ids")
        if payroll_employee_ids is None:
            payroll_employee_ids = [(6, 0, current_payroll_employee_ids)]
        if budget_type != "other":
            values["expense_type_config_id"] = False
            values["service_income_type"] = False
            values["can_cover_payroll"] = False
            values["payroll_employee_ids"] = [(5, 0, 0)]
        elif service_income_type:
            values["expense_type_config_id"] = False
            values["service_income_type"] = service_income_type
            values["can_cover_payroll"] = bool(can_cover_payroll)
            if not (service_income_type == "sales_individual" and can_cover_payroll):
                values["payroll_employee_ids"] = [(5, 0, 0)]
        elif expense_type_config_id:
            values["expense_type_config_id"] = expense_type_config_id
            values["service_income_type"] = False
            values["can_cover_payroll"] = False
            values["payroll_employee_ids"] = [(5, 0, 0)]
        if not values.get("service_income_type"):
            values["can_cover_payroll"] = False
            values["payroll_employee_ids"] = [(5, 0, 0)]
        return values

    def _get_project_active_assignments(self, period):
        self.ensure_one()
        period_date = fields.Date.to_date(period).replace(day=1)
        return self.project_id.assignment_ids.filtered(lambda assignment: assignment._is_active_in_period(period_date))

    def _get_payroll_eligible_employees(self, period):
        self.ensure_one()
        assignments = self._get_project_active_assignments(period)
        employees = assignments.mapped("employee_id")
        if not self.payroll_employee_ids:
            return employees
        return employees & self.payroll_employee_ids

    def _is_employee_payroll_eligible(self, employee, period):
        self.ensure_one()
        employee_record = employee if hasattr(employee, "ids") else self.env["hr.employee"].browse(employee)
        return bool(employee_record and employee_record in self._get_payroll_eligible_employees(period))

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
        detail_label = self._get_detail_label()
        return {
            "budget_line_id": self.id,
            "project_id": self.project_id.id,
            "project_name": self.project_id.display_name,
            "year": self.year,
            "amount": self.amount,
            "name": self.name,
            "label": f"{self.project_id.display_name} / {detail_label}",
            "budget_type": self.budget_type,
            "budget_type_label": dict(self._fields["budget_type"].selection).get(self.budget_type, ""),
            "program_id": self.program_id.id,
            "program_label": self.program_id.display_name or "",
            "expense_type_config_id": self.expense_type_config_id.id or False,
            "expense_type_label": self.expense_type_config_id.display_name or "",
            "service_income_type": self.service_income_type or False,
            "service_income_type_label": dict(self._fields["service_income_type"].selection).get(self.service_income_type, ""),
            "can_cover_payroll": bool(self.can_cover_payroll),
            "detail_label": detail_label,
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

    def action_delete_with_reload(self):
        self.ensure_one()
        self.unlink()
        return {"type": "ir.actions.client", "tag": "soft_reload"}

    @api.model_create_multi
    def create(self, vals_list):
        normalized_vals = [self._normalize_detail_values(vals) for vals in vals_list]
        return super().create(normalized_vals)

    def write(self, vals):
        return super().write(self._normalize_detail_values(vals))
