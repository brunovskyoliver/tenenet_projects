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
    duration = fields.Integer(string="Trvanie (mesiace)", compute="_compute_duration", store=True)
    recipient = fields.Char(string="Príjemca")
    date_contract = fields.Date(string="Dátum zmluvy")
    date_start = fields.Date(string="Začiatok")
    date_end = fields.Date(string="Koniec")
    call_info = fields.Char(string="Výzva")
    partner_id = fields.Many2one("res.partner", string="Partner", ondelete="restrict")
    partners = fields.Char(string="Partneri", related="partner_id.name", store=True, readonly=True)
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
    donor_contact = fields.Text(string="Kontakt donor", compute="_compute_donor_contact", store=True)
    partner_contact = fields.Text(string="Kontakt partner", compute="_compute_partner_contact", store=True)
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

    @api.depends("date_start", "date_end")
    def _compute_duration(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                start_date = min(rec.date_start, rec.date_end)
                end_date = max(rec.date_start, rec.date_end)
                rec.duration = ((end_date.year - start_date.year) * 12) + (
                    end_date.month - start_date.month
                ) + 1
            elif not rec.date_end:
                current_month = fields.Date.today().month
                rec.duration = current_month - rec.date_start.month + 1
            else:
                rec.duration = False

    @api.depends("donor_id.contact_info")
    def _compute_donor_contact(self):
        for rec in self:
            rec.donor_contact = rec.donor_id.contact_info or False

    @api.depends(
        "partner_id",
        "partner_id.name",
        "partner_id.email",
        "partner_id.phone",
        "partner_id.street",
        "partner_id.street2",
        "partner_id.zip",
        "partner_id.city",
        "partner_id.country_id.name",
        "partner_id.website",
    )
    def _compute_partner_contact(self):
        for rec in self:
            rec.partner_contact = rec._format_partner_contact(rec.partner_id)

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

    @api.model
    def _format_partner_contact(self, partner):
        if not partner:
            return False

        lines = []
        if partner.name:
            lines.append(partner.name)
        if partner.email:
            lines.append(partner.email)

        phones = [value for value in [partner.phone] if value]
        if phones:
            lines.append(" / ".join(dict.fromkeys(phones)))

        address_parts = [value for value in [partner.street, partner.street2] if value]
        city_line = " ".join(value for value in [partner.zip, partner.city] if value)
        if city_line:
            address_parts.append(city_line)
        if partner.country_id:
            address_parts.append(partner.country_id.name)
        if address_parts:
            lines.append(", ".join(address_parts))

        if partner.website:
            lines.append(partner.website)

        return "\n".join(lines) if lines else False
