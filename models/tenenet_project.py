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
    allocation_ids = fields.One2many(
        "tenenet.employee.allocation",
        "project_id",
        string="Alokácie",
    )
    receipt_line_ids = fields.One2many(
        "tenenet.project.receipt",
        "project_id",
        string="Prijaté podľa rokov",
    )

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
    active_year_from = fields.Integer(
        string="Rok od",
        compute="_compute_active_year_range",
        store=True,
    )
    active_year_to = fields.Integer(
        string="Rok do",
        compute="_compute_active_year_range",
        store=True,
    )

    @api.depends("date_start", "date_end")
    def _compute_active_year_range(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                rec.active_year_from = min(rec.date_start.year, rec.date_end.year)
                rec.active_year_to = max(rec.date_start.year, rec.date_end.year)
            elif rec.date_start:
                rec.active_year_from = rec.date_start.year
                rec.active_year_to = rec.date_start.year
            elif rec.date_end:
                rec.active_year_from = rec.date_end.year
                rec.active_year_to = rec.date_end.year
            else:
                rec.active_year_from = False
                rec.active_year_to = False

    @api.depends("receipt_line_ids", "receipt_line_ids.amount")
    def _compute_received_total(self):
        for rec in self:
            rec.received_total = sum(rec.receipt_line_ids.mapped("amount"))

    @api.depends("amount_contracted", "received_total")
    def _compute_budget_diff(self):
        for rec in self:
            rec.budget_diff = (rec.amount_contracted or 0.0) - (rec.received_total or 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_receipt_lines()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "date_start" in vals or "date_end" in vals:
            self._sync_receipt_lines()
        return result

    def _sync_receipt_lines(self):
        receipt_model = self.env["tenenet.project.receipt"]
        for rec in self:
            if rec.date_start and rec.date_end:
                start_year = min(rec.date_start.year, rec.date_end.year)
                end_year = max(rec.date_start.year, rec.date_end.year)
            elif rec.date_start:
                start_year = rec.date_start.year
                end_year = rec.date_start.year
            elif rec.date_end:
                start_year = rec.date_end.year
                end_year = rec.date_end.year
            else:
                if rec.receipt_line_ids:
                    rec.receipt_line_ids.unlink()
                continue

            valid_years = set(range(start_year, end_year + 1))
            existing_by_year = {line.year: line for line in rec.receipt_line_ids}

            for year in sorted(valid_years):
                if year not in existing_by_year:
                    receipt_model.create(
                        {
                            "project_id": rec.id,
                            "year": year,
                        }
                    )

            lines_to_remove = rec.receipt_line_ids.filtered(lambda line: line.year not in valid_years)
            if lines_to_remove:
                lines_to_remove.unlink()
