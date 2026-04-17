from odoo import api, fields, models


PHASE_SELECTION = [
    ("pre_hire", "Pred nástupom"),
    ("day_one", "Deň nástupu"),
    ("first_weeks", "Prvé týždne"),
]

PHASE_SEQUENCE = {
    "pre_hire": 10,
    "day_one": 20,
    "first_weeks": 30,
}

RESPONSIBLE_ROLE_SELECTION = [
    ("manager", "Manažér"),
    ("hr", "HR tím"),
    ("operations", "Prevádzka"),
    ("project_manager", "Projektový manažér"),
    ("payroll", "Mzdové oddelenie"),
    ("buddy", "Sprievodca"),
    ("cfo", "CFO"),
    ("ceo", "CEO"),
    ("guarantor", "Odborný garant"),
]


class TenenetOnboardingTaskTemplate(models.Model):
    _name = "tenenet.onboarding.task.template"
    _description = "Šablóna úlohy onboarding procesu"
    _order = "phase_sequence, sequence, id"

    name = fields.Char(
        string="Názov úlohy",
        required=True,
    )
    phase = fields.Selection(
        PHASE_SELECTION,
        string="Fáza",
        required=True,
        default="pre_hire",
    )
    phase_sequence = fields.Integer(
        string="Poradie fázy",
        compute="_compute_phase_sequence",
        store=True,
    )
    sequence = fields.Integer(
        string="Poradie",
        default=10,
    )
    responsible_role = fields.Selection(
        RESPONSIBLE_ROLE_SELECTION,
        string="Zodpovedná rola",
        required=True,
        default="hr",
    )
    is_mandatory = fields.Boolean(
        string="Povinná",
        default=True,
    )
    project_only = fields.Boolean(
        string="Len pre projekty",
        default=False,
        help="Táto úloha sa vygeneruje iba ak je onboarding označený ako projektový.",
    )
    active = fields.Boolean(
        string="Aktívna",
        default=True,
    )

    @api.depends("phase")
    def _compute_phase_sequence(self):
        for tmpl in self:
            tmpl.phase_sequence = PHASE_SEQUENCE.get(tmpl.phase, 99)
