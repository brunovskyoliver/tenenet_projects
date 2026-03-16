from odoo import api, fields, models


class TenenetProject(models.Model):
    _name = "tenenet.project"
    _description = "Projekt TENENET"
    _order = "year desc, name"

    name = fields.Char(string="Názov projektu", required=True)
    code = fields.Char(string="Kód projektu")
    description = fields.Text(string="Popis")
    year = fields.Integer(string="Rok")
    active = fields.Boolean(string="Aktívny", default=True)
    contract_number = fields.Char(string="Číslo zmluvy")
    duration = fields.Char(string="Trvanie")
    recipient = fields.Char(string="Príjemca")
    date_contract = fields.Date(string="Dátum zmluvy")
    date_start = fields.Date(string="Začiatok")
    date_end = fields.Date(string="Koniec")
    call_info = fields.Char(string="Výzva")
    partners = fields.Char(string="Partneri")
    submission_info = fields.Char(string="Podanie")
    portal = fields.Char(string="Portál")
    sustainability = fields.Char(string="Udržateľnosť")

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
    amount_contracted_with_partners = fields.Monetary(
        string="Zmluvná suma vrátane partnerov",
        currency_field="currency_id",
    )
    received_2020 = fields.Monetary(string="Prijaté 2020", currency_field="currency_id")
    received_2021 = fields.Monetary(string="Prijaté 2021", currency_field="currency_id")
    received_2022 = fields.Monetary(string="Prijaté 2022", currency_field="currency_id")
    received_2023 = fields.Monetary(string="Prijaté 2023", currency_field="currency_id")
    received_2024 = fields.Monetary(string="Prijaté 2024", currency_field="currency_id")
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
    settlement_info = fields.Text(string="Zúčtovanie")
    comments = fields.Text(string="Komentáre")
    donor_contact = fields.Text(string="Kontakt donor")
    partner_contact = fields.Text(string="Kontakt partner")
    application_notes = fields.Text(string="Podávanie žiadosti")

    @api.depends(
        "received_2020",
        "received_2021",
        "received_2022",
        "received_2023",
        "received_2024",
        "received_2025",
        "received_2026",
    )
    def _compute_received_total(self):
        for rec in self:
            rec.received_total = (
                (rec.received_2020 or 0.0)
                + (rec.received_2021 or 0.0)
                + (rec.received_2022 or 0.0)
                + (rec.received_2023 or 0.0)
                + (rec.received_2024 or 0.0)
                + (rec.received_2025 or 0.0)
                + (rec.received_2026 or 0.0)
            )

    @api.depends("amount_contracted", "received_total")
    def _compute_budget_diff(self):
        for rec in self:
            rec.budget_diff = (rec.amount_contracted or 0.0) - (rec.received_total or 0.0)
