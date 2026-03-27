from odoo import api, fields, models
from odoo.exceptions import ValidationError


ALERT_ALLOWED_FIELD_TYPES = (
    "date",
    "datetime",
    "char",
    "text",
    "integer",
    "float",
    "monetary",
    "boolean",
    "selection",
    "many2one",
)

ALERT_TEXT_OPERATORS = (
    ("contains", "Obsahuje"),
    ("not_contains", "Neobsahuje"),
    ("equals", "Rovná sa"),
    ("not_equals", "Nerovná sa"),
    ("is_set", "Je vyplnené"),
    ("is_not_set", "Nie je vyplnené"),
)
ALERT_NUMERIC_OPERATORS = (
    ("eq", "="),
    ("ne", "!="),
    ("gt", ">"),
    ("ge", ">="),
    ("lt", "<"),
    ("le", "<="),
    ("is_set", "Je vyplnené"),
    ("is_not_set", "Nie je vyplnené"),
)
ALERT_BOOLEAN_OPERATORS = (
    ("is_true", "Áno"),
    ("is_false", "Nie"),
)
ALERT_SELECTION_OPERATORS = (
    ("eq", "="),
    ("ne", "!="),
    ("is_set", "Je vyplnené"),
    ("is_not_set", "Nie je vyplnené"),
)
ALERT_MANY2ONE_OPERATORS = (
    ("eq", "="),
    ("ne", "!="),
    ("is_set", "Je vyplnené"),
    ("is_not_set", "Nie je vyplnené"),
)
ALERT_DATE_STATIC_OPERATORS = (
    ("eq", "="),
    ("ne", "!="),
    ("gt", ">"),
    ("ge", ">="),
    ("lt", "<"),
    ("le", "<="),
    ("is_set", "Je vyplnené"),
    ("is_not_set", "Nie je vyplnené"),
)
ALERT_DATE_RELATIVE_OPERATORS = (
    ("within_next", "V najbližších"),
    ("within_last", "V posledných"),
    ("older_than", "Staršie než"),
    ("younger_than", "Mladšie než"),
    ("today", "Dnes"),
    ("overdue", "Po termíne"),
)

ALERT_OPERATOR_SELECTION = (
    ALERT_TEXT_OPERATORS
    + ALERT_NUMERIC_OPERATORS
    + ALERT_BOOLEAN_OPERATORS
    + ALERT_SELECTION_OPERATORS
    + ALERT_MANY2ONE_OPERATORS
    + ALERT_DATE_STATIC_OPERATORS
    + ALERT_DATE_RELATIVE_OPERATORS
)


class TenenetAlertCondition(models.Model):
    _name = "tenenet.alert.condition"
    _description = "Podmienka upozornenia"
    _order = "sequence, id"

    sequence = fields.Integer(string="Poradie", default=10)
    rule_id = fields.Many2one(
        "tenenet.alert.rule",
        string="Pravidlo",
        required=True,
        ondelete="cascade",
    )
    field_id = fields.Many2one(
        "ir.model.fields",
        string="Pole",
        required=True,
        ondelete="restrict",
        domain="[('model_id', '=', rule_id.model_id), ('store', '=', True), ('ttype', 'in', allowed_field_types)]",
    )
    field_name = fields.Char(string="Technický názov poľa", related="field_id.name", store=True, readonly=True)
    field_ttype = fields.Selection(string="Typ poľa", related="field_id.ttype", store=True, readonly=True)
    value_mode = fields.Selection(
        [("static", "Statická"), ("relative", "Relatívna")],
        string="Typ hodnoty",
        required=True,
        default="static",
    )
    operator = fields.Selection(ALERT_OPERATOR_SELECTION, string="Operátor", required=True)
    value_char = fields.Char(string="Textová hodnota")
    value_text = fields.Text(string="Textová hodnota")
    value_float = fields.Float(string="Číselná hodnota")
    value_integer = fields.Integer(string="Celé číslo")
    value_boolean = fields.Boolean(string="Logická hodnota")
    value_date = fields.Date(string="Dátum")
    value_datetime = fields.Datetime(string="Dátum a čas")
    value_selection_key = fields.Char(string="Kľúč výberu")
    value_reference = fields.Reference(
        string="Súvisiaci záznam",
        selection="_selection_reference_models",
    )
    relative_direction = fields.Selection(
        [("past", "Do minulosti"), ("future", "Do budúcnosti")],
        string="Smer",
        default="future",
    )
    relative_amount = fields.Integer(string="Počet", default=1)
    relative_unit = fields.Selection(
        [("day", "Dni"), ("week", "Týždne"), ("month", "Mesiace")],
        string="Jednotka",
        default="day",
    )
    allowed_field_types = fields.Char(compute="_compute_allowed_field_types")
    allowed_operator_codes = fields.Char(compute="_compute_allowed_operator_codes")
    comodel_name = fields.Char(string="Súvisiaci model", related="field_id.relation", readonly=True)

    @api.depends_context("uid")
    def _compute_allowed_field_types(self):
        value = ",".join(ALERT_ALLOWED_FIELD_TYPES)
        for rec in self:
            rec.allowed_field_types = value

    @api.depends("field_id", "field_ttype", "value_mode")
    def _compute_allowed_operator_codes(self):
        for rec in self:
            operators = rec._get_operator_codes_for_field()
            rec.allowed_operator_codes = ",".join(operators)

    @api.model
    def _selection_reference_models(self):
        models_data = self.env["ir.model"].search([("transient", "=", False)])
        return [(model.model, model.name) for model in models_data]

    def _get_operator_codes_for_field(self):
        self.ensure_one()
        field_type = self.field_ttype
        if field_type in {"char", "text"}:
            return [code for code, _label in ALERT_TEXT_OPERATORS]
        if field_type in {"integer", "float", "monetary"}:
            return [code for code, _label in ALERT_NUMERIC_OPERATORS]
        if field_type == "boolean":
            return [code for code, _label in ALERT_BOOLEAN_OPERATORS]
        if field_type == "selection":
            return [code for code, _label in ALERT_SELECTION_OPERATORS]
        if field_type == "many2one":
            return [code for code, _label in ALERT_MANY2ONE_OPERATORS]
        if field_type in {"date", "datetime"}:
            source = ALERT_DATE_RELATIVE_OPERATORS if self.value_mode == "relative" else ALERT_DATE_STATIC_OPERATORS
            return [code for code, _label in source]
        return []

    @api.onchange("field_id")
    def _onchange_field_id(self):
        for rec in self:
            if not rec.field_id:
                continue
            rec.value_mode = "static"
            operators = rec._get_operator_codes_for_field()
            rec.operator = operators[0] if operators else False
            rec._reset_value_fields()

    @api.onchange("value_mode")
    def _onchange_value_mode(self):
        for rec in self:
            if not rec.field_id:
                continue
            operators = rec._get_operator_codes_for_field()
            if rec.operator not in operators:
                rec.operator = operators[0] if operators else False

    def _reset_value_fields(self):
        self.update({
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
        })

    @api.constrains("field_id", "rule_id")
    def _check_field_allowed(self):
        for rec in self:
            if not rec.field_id or not rec.rule_id.model_id:
                continue
            if rec.field_id.model_id != rec.rule_id.model_id:
                raise ValidationError("Pole musí patriť do vybraného modelu upozornenia.")
            if rec.field_id.ttype not in ALERT_ALLOWED_FIELD_TYPES:
                raise ValidationError("Vybraný typ poľa ešte nie je v upozorneniach podporovaný.")
            if not rec.field_id.store:
                raise ValidationError("Pre upozornenia je možné použiť len uložené polia.")

    @api.constrains("operator", "field_id", "value_mode")
    def _check_operator_supported(self):
        for rec in self:
            if rec.operator and rec.operator not in rec._get_operator_codes_for_field():
                raise ValidationError("Zvolený operátor nie je pre tento typ poľa podporovaný.")

    @api.constrains("field_id", "operator", "value_mode", "relative_amount")
    def _check_required_value(self):
        for rec in self:
            if not rec.field_id or not rec.operator:
                continue
            if rec.operator in {"is_set", "is_not_set", "is_true", "is_false", "today", "overdue"}:
                continue
            if rec.value_mode == "relative":
                if rec.field_ttype not in {"date", "datetime"}:
                    raise ValidationError("Relatívne podmienky je možné použiť len na dátumové polia.")
                if rec.relative_amount <= 0:
                    raise ValidationError("Relatívna podmienka musí mať kladný počet jednotiek.")
                continue
            if rec.field_ttype in {"char"} and rec.value_char in {False, ""}:
                raise ValidationError("Textová podmienka vyžaduje hodnotu.")
            if rec.field_ttype == "text" and rec.value_text in {False, ""}:
                raise ValidationError("Textová podmienka vyžaduje hodnotu.")
            if rec.field_ttype in {"integer"} and rec.value_integer is False:
                raise ValidationError("Číselná podmienka vyžaduje hodnotu.")
            if rec.field_ttype in {"float", "monetary"} and rec.value_float is False:
                raise ValidationError("Číselná podmienka vyžaduje hodnotu.")
            if rec.field_ttype == "selection" and not rec.value_selection_key:
                raise ValidationError("Výberová podmienka vyžaduje hodnotu.")
            if rec.field_ttype == "many2one" and not rec.value_reference:
                raise ValidationError("Vzťahová podmienka vyžaduje vybraný záznam.")
            if rec.field_ttype == "date" and not rec.value_date:
                raise ValidationError("Dátumová podmienka vyžaduje dátum.")
            if rec.field_ttype == "datetime" and not rec.value_datetime:
                raise ValidationError("Dátumová podmienka vyžaduje dátum a čas.")
