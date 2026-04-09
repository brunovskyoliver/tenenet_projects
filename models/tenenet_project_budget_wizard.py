from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TenenetProjectBudgetWizard(models.TransientModel):
    _name = "tenenet.project.budget.wizard"
    _description = "Sprievodca pridaním rozpočtovej položky projektu"

    project_id = fields.Many2one("tenenet.project", string="Projekt", required=True, readonly=True)
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
    )
    available_program_ids = fields.Many2many(
        "tenenet.program",
        compute="_compute_available_program_ids",
    )
    name = fields.Char(string="Názov položky", required=True)
    input_mode = fields.Selection(
        [
            ("amount", "Suma"),
            ("percentage", "Percento"),
        ],
        string="Spôsob zadania",
        default="amount",
        required=True,
    )
    allocation_percentage = fields.Float(
        string="Alokovať (%)",
        digits=(6, 2),
        default=0.0,
    )
    amount = fields.Monetary(string="Suma", currency_field="currency_id", required=True, default=0.0)
    note = fields.Text(string="Poznámka")
    currency_id = fields.Many2one(
        "res.currency",
        related="project_id.currency_id",
        readonly=True,
    )
    year_received_amount = fields.Monetary(
        string="Prijaté financie za rok",
        currency_field="currency_id",
        compute="_compute_amounts",
    )
    year_budgeted_amount = fields.Monetary(
        string="Rozpočtované za rok",
        currency_field="currency_id",
        compute="_compute_amounts",
    )
    available_amount = fields.Monetary(
        string="Ešte dostupné",
        currency_field="currency_id",
        compute="_compute_amounts",
    )
    allocation_summary_html = fields.Html(
        string="Aktuálne alokačné % programov",
        compute="_compute_allocation_summary_html",
        sanitize=False,
    )

    @api.depends("project_id", "budget_type")
    def _compute_available_program_ids(self):
        for rec in self:
            admin_program = self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1)
            if rec.budget_type == "pausal":
                rec.available_program_ids = admin_program
            else:
                rec.available_program_ids = rec.project_id.program_ids.filtered(lambda program: program != admin_program)

    @api.depends("project_id", "year")
    def _compute_amounts(self):
        for rec in self:
            if not rec.project_id or not rec.year:
                rec.year_received_amount = 0.0
                rec.year_budgeted_amount = 0.0
                rec.available_amount = 0.0
                continue
            received = sum(rec.project_id.receipt_line_ids.filtered(lambda line: line.year == rec.year).mapped("amount"))
            budgeted = sum(rec.project_id.budget_line_ids.filtered(lambda line: line.year == rec.year).mapped("amount"))
            rec.year_received_amount = received
            rec.year_budgeted_amount = budgeted
            rec.available_amount = received - budgeted

    @api.depends("project_id")
    def _compute_allocation_summary_html(self):
        for rec in self:
            rows = rec.project_id._get_current_program_allocation_rows()
            if not rows:
                rec.allocation_summary_html = "<p>Pre projekt zatiaľ nie sú dostupné alokačné dáta.</p>"
                continue
            items = "".join(
                f"<li><strong>{row['program'].display_name}</strong>: {row['allocation_pct']:.2f} %"
                f" ({row['allocation_ratio']:.2f} % úväzku)</li>"
                for row in rows
            )
            rec.allocation_summary_html = f"<ul>{items}</ul>"

    @api.onchange("project_id", "budget_type")
    def _onchange_defaults(self):
        domain = {"program_id": [("id", "in", self.available_program_ids.ids)]}
        for rec in self:
            admin_program = self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1)
            rows = rec.project_id._get_current_program_allocation_rows()
            if rec.budget_type == "pausal":
                rec.program_id = admin_program
            elif rows:
                rec.program_id = rows[0]["program"]
            else:
                rec.program_id = rec.project_id.reporting_program_id or rec.project_id.program_ids[:1]
        return {"domain": domain}

    def _sync_amount_from_percentage(self):
        for rec in self:
            available = rec.available_amount or 0.0
            if available <= 0.0:
                rec.amount = 0.0
                continue
            rec.amount = rec.currency_id.round(available * ((rec.allocation_percentage or 0.0) / 100.0))

    def _sync_percentage_from_amount(self):
        for rec in self:
            available = rec.available_amount or 0.0
            if available <= 0.0:
                rec.allocation_percentage = 0.0
                continue
            rec.allocation_percentage = ((rec.amount or 0.0) / available) * 100.0

    @api.onchange("allocation_percentage")
    def _onchange_allocation_percentage(self):
        for rec in self:
            rec.input_mode = "percentage"
        self._sync_amount_from_percentage()

    @api.onchange("amount")
    def _onchange_amount(self):
        for rec in self:
            rec.input_mode = "amount"
        self._sync_percentage_from_amount()

    @api.onchange("project_id", "year")
    def _onchange_amount_basis(self):
        for rec in self:
            if rec.input_mode == "percentage":
                rec._sync_amount_from_percentage()
            else:
                rec._sync_percentage_from_amount()

    def action_confirm(self):
        self.ensure_one()
        if self.input_mode == "percentage":
            self._sync_amount_from_percentage()
        else:
            self._sync_percentage_from_amount()
        if self.allocation_percentage < 0.0 or self.allocation_percentage > 100.0:
            raise ValidationError("Percento alokácie musí byť medzi 0 a 100.")
        if self.amount <= 0.0:
            raise ValidationError("Rozpočtová položka musí mať kladnú sumu.")
        if self.amount > self.available_amount:
            raise ValidationError("Rozpočtová položka prekračuje dostupné prijaté financie za zvolený rok.")
        self.env["tenenet.project.budget.line"].create({
            "project_id": self.project_id.id,
            "year": self.year,
            "budget_type": self.budget_type,
            "program_id": (
                self.env["tenenet.program"].search([("code", "=", "ADMIN_TENENET")], limit=1).id
                if self.budget_type == "pausal"
                else self.program_id.id
            ),
            "name": self.name,
            "amount": self.amount,
            "note": self.note,
        })
        return {"type": "ir.actions.act_window_close"}
