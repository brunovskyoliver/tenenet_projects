from odoo import api, fields, models


class TenenetProject(models.Model):
    _name = "tenenet.project"
    _description = "Projekt TENENET"
    _order = "year desc, name"

    name = fields.Char(string="Názov projektu", required=True)
    code = fields.Char(string="Kód projektu")
    year = fields.Integer(string="Rok")
    active = fields.Boolean(string="Aktívny", default=True)
    contract_number = fields.Char(string="Číslo zmluvy")
    recipient = fields.Char(string="Príjemca")
    date_start = fields.Date(string="Začiatok")
    date_end = fields.Date(string="Koniec")

    semaphore = fields.Selection(
        [("green", "Zelená"), ("yellow", "Žltá"), ("red", "Červená")],
        string="Semafor",
    )

    program_id = fields.Many2one("tenenet.program", string="Program", ondelete="restrict")
    donor_id = fields.Many2one("tenenet.donor", string="Donor", ondelete="restrict")

    program_director_id = fields.Many2one("hr.employee", string="Programový riaditeľ")
    project_manager_id = fields.Many2one("hr.employee", string="Projektový manažér")
    financial_manager_id = fields.Many2one("hr.employee", string="Finančný manažér")

    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
    )
    budget_total = fields.Monetary(string="Celkový rozpočet", currency_field="currency_id")
    amount_contracted = fields.Monetary(string="Zmluvná suma", currency_field="currency_id")
    received_2025 = fields.Monetary(string="Prijaté 2025", currency_field="currency_id")
    received_2026 = fields.Monetary(string="Prijaté 2026", currency_field="currency_id")
    received_total = fields.Monetary(
        string="Prijaté spolu",
        currency_field="currency_id",
        compute="_compute_received_total",
        store=True,
    )
    budget_diff = fields.Monetary(
        string="Rozdiel",
        currency_field="currency_id",
        compute="_compute_budget_diff",
        store=True,
    )

    @api.depends("received_2025", "received_2026")
    def _compute_received_total(self):
        for rec in self:
            rec.received_total = (rec.received_2025 or 0.0) + (rec.received_2026 or 0.0)

    @api.depends("amount_contracted", "received_total")
    def _compute_budget_diff(self):
        for rec in self:
            rec.budget_diff = (rec.amount_contracted or 0.0) - (rec.received_total or 0.0)
