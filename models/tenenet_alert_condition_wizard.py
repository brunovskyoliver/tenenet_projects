from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .tenenet_alert_condition import (
    ALERT_BOOLEAN_OPERATORS,
    ALERT_DATE_RELATIVE_OPERATORS,
    ALERT_DATE_STATIC_OPERATORS,
    ALERT_MANY2ONE_OPERATORS,
    ALERT_NUMERIC_OPERATORS,
    ALERT_SELECTION_OPERATORS,
    ALERT_TEXT_OPERATORS,
)


RELATIVE_DATE_OPERATOR_CODES = {code for code, _label in ALERT_DATE_RELATIVE_OPERATORS}


class TenenetAlertConditionWizard(models.TransientModel):
    _name = "tenenet.alert.condition.wizard"
    _description = "Sprievodca podmienkou upozornenia"

    rule_id = fields.Many2one("tenenet.alert.rule", string="Pravidlo", required=True)
    target_model_id = fields.Many2one("ir.model", string="Model upozornenia", related="rule_id.model_id", readonly=True)
    condition_id = fields.Many2one("tenenet.alert.condition", string="Upravovaná podmienka")
    sequence = fields.Integer(string="Poradie", default=10)
    field_id = fields.Many2one(
        "ir.model.fields",
        string="Pole",
        required=True,
    )
    field_ttype = fields.Selection(related="field_id.ttype", readonly=True)
    comodel_name = fields.Char(string="Súvisiaci model", related="field_id.relation", readonly=True)

    operator_text = fields.Selection(ALERT_TEXT_OPERATORS, string="Textová podmienka")
    operator_numeric = fields.Selection(ALERT_NUMERIC_OPERATORS, string="Číselná podmienka")
    operator_boolean = fields.Selection(ALERT_BOOLEAN_OPERATORS, string="Logická podmienka")
    operator_selection = fields.Selection(ALERT_SELECTION_OPERATORS, string="Výberová podmienka")
    operator_many2one = fields.Selection(ALERT_MANY2ONE_OPERATORS, string="Vzťahová podmienka")
    operator_date = fields.Selection(ALERT_DATE_STATIC_OPERATORS + ALERT_DATE_RELATIVE_OPERATORS, string="Dátumová podmienka")

    value_char = fields.Char(string="Krátky text")
    value_text = fields.Text(string="Dlhší text")
    value_float = fields.Float(string="Číslo")
    value_integer = fields.Integer(string="Celé číslo")
    value_selection_key = fields.Char(string="Kľúč výberu")
    selection_item_id = fields.Many2one(
        "ir.model.fields.selection",
        string="Hodnota výberu",
        domain="[('field_id', '=', field_id)]",
        ondelete="cascade",
    )
    value_reference = fields.Reference(
        string="Súvisiaci záznam",
        selection="_selection_reference_models",
    )
    value_date = fields.Date(string="Dátum")
    value_datetime = fields.Datetime(string="Dátum a čas")
    relative_amount = fields.Integer(string="Počet", default=1)
    relative_unit = fields.Selection(
        [("day", "Dni"), ("week", "Týždne"), ("month", "Mesiace")],
        string="Jednotka",
        default="day",
    )

    operator_code = fields.Char(compute="_compute_operator_code")
    show_text_value = fields.Boolean(compute="_compute_visibility_flags")
    show_textarea_value = fields.Boolean(compute="_compute_visibility_flags")
    show_integer_value = fields.Boolean(compute="_compute_visibility_flags")
    show_float_value = fields.Boolean(compute="_compute_visibility_flags")
    show_selection_value = fields.Boolean(compute="_compute_visibility_flags")
    show_reference_value = fields.Boolean(compute="_compute_visibility_flags")
    show_date_value = fields.Boolean(compute="_compute_visibility_flags")
    show_datetime_value = fields.Boolean(compute="_compute_visibility_flags")
    show_relative_value = fields.Boolean(compute="_compute_visibility_flags")

    @api.model
    def _selection_reference_models(self):
        models_data = self.env["ir.model"].search([("transient", "=", False)])
        return [(model.model, model.name) for model in models_data]

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        condition = False
        condition_id = self.env.context.get("default_condition_id")
        if condition_id:
            condition = self.env["tenenet.alert.condition"].browse(condition_id)
        if not condition:
            return values
        values.update({
            "rule_id": condition.rule_id.id,
            "condition_id": condition.id,
            "sequence": condition.sequence,
            "field_id": condition.field_id.id,
            "value_char": condition.value_char,
            "value_text": condition.value_text,
            "value_float": condition.value_float,
            "value_integer": condition.value_integer,
            "value_selection_key": condition.value_selection_key,
            "value_reference": "%s,%s" % (condition.value_reference._name, condition.value_reference.id) if condition.value_reference else False,
            "value_date": condition.value_date,
            "value_datetime": condition.value_datetime,
            "relative_amount": condition.relative_amount,
            "relative_unit": condition.relative_unit,
        })
        if condition.field_id.ttype == "selection":
            selection_item = condition.field_id.selection_ids.filtered(lambda item: item.value == condition.value_selection_key)[:1]
            values["selection_item_id"] = selection_item.id
        operator_field = self._operator_field_name(condition.field_id.ttype)
        if operator_field:
            values[operator_field] = condition.operator
        return values

    @api.depends(
        "field_ttype",
        "operator_text",
        "operator_numeric",
        "operator_boolean",
        "operator_selection",
        "operator_many2one",
        "operator_date",
    )
    def _compute_operator_code(self):
        for rec in self:
            operator_field = rec._operator_field_name(rec.field_ttype)
            rec.operator_code = rec[operator_field] if operator_field else False

    @api.depends("field_ttype", "operator_code")
    def _compute_visibility_flags(self):
        no_value_ops = {"is_set", "is_not_set", "is_true", "is_false", "today", "overdue"}
        for rec in self:
            op = rec.operator_code
            needs_value = op not in no_value_ops
            rec.show_text_value = rec.field_ttype == "char" and needs_value
            rec.show_textarea_value = rec.field_ttype == "text" and needs_value
            rec.show_integer_value = rec.field_ttype == "integer" and needs_value
            rec.show_float_value = rec.field_ttype in {"float", "monetary"} and needs_value
            rec.show_selection_value = rec.field_ttype == "selection" and needs_value
            rec.show_reference_value = rec.field_ttype == "many2one" and needs_value
            rec.show_date_value = rec.field_ttype == "date" and needs_value and op not in RELATIVE_DATE_OPERATOR_CODES
            rec.show_datetime_value = rec.field_ttype == "datetime" and needs_value and op not in RELATIVE_DATE_OPERATOR_CODES
            rec.show_relative_value = rec.field_ttype in {"date", "datetime"} and op in RELATIVE_DATE_OPERATOR_CODES - {"today", "overdue"}

    @api.onchange("field_id")
    def _onchange_field_id(self):
        for rec in self:
            rec.operator_text = False
            rec.operator_numeric = False
            rec.operator_boolean = False
            rec.operator_selection = False
            rec.operator_many2one = False
            rec.operator_date = False
            rec.value_char = False
            rec.value_text = False
            rec.value_float = 0.0
            rec.value_integer = 0
            rec.value_selection_key = False
            rec.selection_item_id = False
            rec.value_reference = False
            rec.value_date = False
            rec.value_datetime = False
            rec.relative_amount = 1
            rec.relative_unit = "day"
            operator_field = rec._operator_field_name(rec.field_ttype)
            if operator_field:
                rec[operator_field] = rec._default_operator_for_type()

    @api.onchange("selection_item_id")
    def _onchange_selection_item_id(self):
        for rec in self:
            rec.value_selection_key = rec.selection_item_id.value if rec.selection_item_id else False

    def _operator_field_name(self, field_ttype):
        mapping = {
            "char": "operator_text",
            "text": "operator_text",
            "integer": "operator_numeric",
            "float": "operator_numeric",
            "monetary": "operator_numeric",
            "boolean": "operator_boolean",
            "selection": "operator_selection",
            "many2one": "operator_many2one",
            "date": "operator_date",
            "datetime": "operator_date",
        }
        return mapping.get(field_ttype)

    def _default_operator_for_type(self):
        self.ensure_one()
        defaults = {
            "char": ALERT_TEXT_OPERATORS[0][0],
            "text": ALERT_TEXT_OPERATORS[0][0],
            "integer": ALERT_NUMERIC_OPERATORS[0][0],
            "float": ALERT_NUMERIC_OPERATORS[0][0],
            "monetary": ALERT_NUMERIC_OPERATORS[0][0],
            "boolean": ALERT_BOOLEAN_OPERATORS[0][0],
            "selection": ALERT_SELECTION_OPERATORS[0][0],
            "many2one": ALERT_MANY2ONE_OPERATORS[0][0],
            "date": ALERT_DATE_RELATIVE_OPERATORS[0][0],
            "datetime": ALERT_DATE_RELATIVE_OPERATORS[0][0],
        }
        return defaults.get(self.field_ttype)

    def _prepare_condition_values(self):
        self.ensure_one()
        operator = self.operator_code
        if not self.field_id or not operator:
            raise ValidationError("Vyplňte pole a podmienku.")
        values = {
            "rule_id": self.rule_id.id,
            "sequence": self.sequence,
            "field_id": self.field_id.id,
            "operator": operator,
            "value_mode": "relative" if operator in RELATIVE_DATE_OPERATOR_CODES else "static",
            "value_char": False,
            "value_text": False,
            "value_float": 0.0,
            "value_integer": 0,
            "value_boolean": False,
            "value_date": False,
            "value_datetime": False,
            "value_selection_key": False,
            "value_reference": False,
            "relative_direction": "future",
            "relative_amount": 1,
            "relative_unit": "day",
        }
        if self.field_ttype == "char":
            values["value_char"] = self.value_char
        elif self.field_ttype == "text":
            values["value_text"] = self.value_text
        elif self.field_ttype == "integer":
            values["value_integer"] = self.value_integer
        elif self.field_ttype in {"float", "monetary"}:
            values["value_float"] = self.value_float
        elif self.field_ttype == "selection":
            values["value_selection_key"] = self.selection_item_id.value or self.value_selection_key
        elif self.field_ttype == "many2one":
            values["value_reference"] = self.value_reference and "%s,%s" % (self.value_reference._name, self.value_reference.id)
        elif self.field_ttype == "date":
            if operator in RELATIVE_DATE_OPERATOR_CODES:
                values["relative_amount"] = self.relative_amount
                values["relative_unit"] = self.relative_unit
            else:
                values["value_date"] = self.value_date
        elif self.field_ttype == "datetime":
            if operator in RELATIVE_DATE_OPERATOR_CODES:
                values["relative_amount"] = self.relative_amount
                values["relative_unit"] = self.relative_unit
            else:
                values["value_datetime"] = self.value_datetime
        return values

    def action_save(self):
        self.ensure_one()
        values = self._prepare_condition_values()
        if self.condition_id:
            self.condition_id.write(values)
        else:
            self.env["tenenet.alert.condition"].create(values)
        return {"type": "ir.actions.client", "tag": "reload"}
