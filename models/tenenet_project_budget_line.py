from odoo import api, fields, models
from odoo.exceptions import ValidationError


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

    @api.constrains("amount")
    def _check_non_negative_amount(self):
        for rec in self:
            if rec.amount < 0.0:
                raise ValidationError("Rozpočtová položka nemôže mať zápornú sumu.")

    @api.constrains("project_id", "program_id")
    def _check_program_belongs_to_project(self):
        for rec in self:
            if not rec.project_id or not rec.program_id:
                continue
            if rec.project_id.is_tenenet_internal:
                if rec.program_id.code != "ADMIN_TENENET":
                    raise ValidationError("Interný projekt môže používať iba program Admin TENENET.")
                continue
            if rec.program_id not in rec.project_id.program_ids:
                raise ValidationError("Program rozpočtovej položky musí patriť medzi programy projektu.")
