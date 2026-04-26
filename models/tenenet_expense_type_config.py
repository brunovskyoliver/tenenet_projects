from odoo import Command, api, fields, models


OPERATING_EXPENSE_CONFIGS = [
    {
        "seed_key": "operating_rent",
        "name": "Nájom",
        "sequence": 100,
        "tenenet_usage": "operating",
        "cashflow_row_key": "workbook:expense:prevadzkove-n-najom",
        "cashflow_row_label": "Prevádzkové náklady - nájom",
        "admin_pl_row_key": "operating:rent",
        "admin_pl_row_label": "Nájom",
    },
    {
        "seed_key": "operating_energy",
        "name": "Energie",
        "sequence": 110,
        "tenenet_usage": "operating",
        "cashflow_row_key": "workbook:expense:prevadzkove-n-energie",
        "cashflow_row_label": "Prevádzkové náklady - energie",
        "admin_pl_row_key": "operating:energy",
        "admin_pl_row_label": "Energie",
    },
    {
        "seed_key": "operating_it",
        "name": "IT / software / tlačiarne",
        "sequence": 120,
        "tenenet_usage": "operating",
        "cashflow_row_key": "workbook:expense:prevadzkove-n-it-slu-tlaciarne-dv",
        "cashflow_row_label": "Prevádzkové náklady - IT služby a tlačiarne (DV)",
        "admin_pl_row_key": "operating:it",
        "admin_pl_row_label": "IT / software / tlačiarne",
    },
    {
        "seed_key": "operating_telecom",
        "name": "Telekom / internet",
        "sequence": 130,
        "tenenet_usage": "operating",
        "cashflow_row_key": "workbook:expense:prevadzkove-n-tel-a-internet",
        "cashflow_row_label": "Prevádzkové náklady - telekomunikácie a internet",
        "admin_pl_row_key": "operating:telecom",
        "admin_pl_row_label": "Telekom / internet",
    },
    {
        "seed_key": "operating_legal_audit",
        "name": "Právne / audit",
        "sequence": 140,
        "tenenet_usage": "operating",
        "cashflow_row_key": "workbook:expense:prevadzkove-n-pravne-sluzby-cls-audit-jp",
        "cashflow_row_label": "Prevádzkové náklady - právne služby (CLS) a audit (JP)",
        "admin_pl_row_key": "operating:legal_audit",
        "admin_pl_row_label": "Právne / audit",
    },
    {
        "seed_key": "operating_hr_training",
        "name": "HR / vzdelávanie / supervízia",
        "sequence": 150,
        "tenenet_usage": "operating",
        "cashflow_row_key": "workbook:expense:prevadzkova-n-hr-costs-vzdelavanie-superv-a-sk",
        "cashflow_row_label": "Prevádzkové náklady - HR, vzdelávanie a supervízia",
        "admin_pl_row_key": "operating:hr_training",
        "admin_pl_row_label": "HR / vzdelávanie / supervízia",
    },
    {
        "seed_key": "operating_pr_marketing",
        "name": "PR / marketing",
        "sequence": 160,
        "tenenet_usage": "operating",
        "cashflow_row_key": "workbook:expense:prevadzkova-n-market-pr-costs-tt",
        "cashflow_row_label": "Prevádzkové náklady - marketing a PR",
        "admin_pl_row_key": "operating:pr_marketing",
        "admin_pl_row_label": "PR / marketing",
    },
    {
        "seed_key": "operating_insurance",
        "name": "Poistenie",
        "sequence": 170,
        "tenenet_usage": "operating",
        "cashflow_row_key": "workbook:expense:prevadzkove-n-auta-poistenie-opravy-poistenie-budov",
        "cashflow_row_label": "Prevádzkové náklady - poistenie a opravy, poistenie budov",
        "admin_pl_row_key": "operating:insurance",
        "admin_pl_row_label": "Poistenie",
    },
    {
        "seed_key": "operating_taxes_fees_cards",
        "name": "Dane / poplatky / platby kartou",
        "sequence": 180,
        "tenenet_usage": "operating",
        "cashflow_row_key": "workbook:expense:prevadzkove-n-one-off-items-vo-dane",
        "cashflow_row_label": "Prevádzkové náklady - dane, poplatky a jednorazové položky",
        "admin_pl_row_key": "operating:taxes_fees_cards",
        "admin_pl_row_label": "Dane / poplatky / platby kartou",
    },
    {
        "seed_key": "operating_other",
        "name": "Ostatné prevádzkové",
        "sequence": 190,
        "tenenet_usage": "operating",
        "cashflow_row_key": "workbook:expense:prevadzkove-n-other-general-costs-n-m",
        "cashflow_row_label": "Prevádzkové náklady - ostatné všeobecné náklady",
        "admin_pl_row_key": "operating:other",
        "admin_pl_row_label": "Ostatné prevádzkové",
    },
]

OPERATING_DETAIL_LABEL_ALIASES = {
    "najom": "operating_rent",
    "hl najom": "operating_rent",
    "dodo najom": "operating_rent",
    "energie": "operating_energy",
    "it slu": "operating_it",
    "microsoft": "operating_it",
    "telekom slu": "operating_telecom",
    "pravne slu": "operating_legal_audit",
    "hr": "operating_hr_training",
    "hr eye am": "operating_hr_training",
    "vzdelavanie": "operating_hr_training",
    "pr": "operating_pr_marketing",
    "poistovna": "operating_insurance",
    "poistenie": "operating_insurance",
    "dan miestna": "operating_taxes_fees_cards",
    "dan z nehnutelnosti": "operating_taxes_fees_cards",
    "poplatok": "operating_taxes_fees_cards",
    "platba kartou": "operating_taxes_fees_cards",
    "platby kartou": "operating_taxes_fees_cards",
    "ostatne": "operating_other",
    "ambulancie": "operating_other",
    "assp": "operating_other",
    "eirr": "operating_other",
    "pas zilina": "operating_other",
    "psc": "operating_other",
    "projekt cdr": "operating_other",
    "wellnea admin slu": "operating_other",
}


class TenenetExpenseTypeConfig(models.Model):
    _name = "tenenet.expense.type.config"
    _description = "Typ projektového nákladu (katalóg)"
    _order = "sequence, name"

    name = fields.Char(string="Názov typu nákladu", required=True)
    description = fields.Text(string="Popis")
    sequence = fields.Integer(string="Poradie", default=10)
    active = fields.Boolean(string="Aktívny", default=True)
    seed_key = fields.Char(string="Seed key", copy=False, index=True)
    tenenet_usage = fields.Selection(
        [
            ("project", "Projektový"),
            ("operating", "Prevádzkový"),
            ("both", "Oba"),
        ],
        string="Použitie",
        required=True,
        default="project",
    )
    expense_category_line_ids = fields.One2many(
        "tenenet.expense.type.config.category",
        "config_id",
        string="Kategórie HR výdavkov",
    )
    hr_expense_product_id = fields.Many2one(
        "product.product",
        string="HR kategória výdavku",
        domain=[("can_be_expensed", "=", True)],
    )
    cashflow_row_key = fields.Char(
        string="Cashflow riadok",
        help="Voliteľný kľúč cashflow riadku, do ktorého sa tento typ výdavku mapuje ako skutočnosť.",
    )
    cashflow_row_label = fields.Char(
        string="Cashflow riadok - názov",
        help="Kanónický názov riadku v cashflow reporte.",
    )
    admin_pl_row_key = fields.Char(
        string="Admin P&L riadok",
        help="Kľúč detailného riadku v Admin TENENET P&L.",
    )
    admin_pl_row_label = fields.Char(
        string="Admin P&L riadok - názov",
        help="Zobrazovaný názov detailného riadku v Admin TENENET P&L.",
    )

    _unique_seed_key = models.Constraint(
        "UNIQUE(seed_key)",
        "Seed key typu nákladu musí byť unikátny.",
    )

    @api.onchange("hr_expense_product_id")
    def _onchange_hr_expense_product_id(self):
        for rec in self:
            rec._sync_primary_category_line()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_primary_category_line()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "hr_expense_product_id" in vals:
            self._sync_primary_category_line()
        return result

    def _get_primary_expense_category(self):
        self.ensure_one()
        if self.hr_expense_product_id:
            return self.hr_expense_product_id
        return self.expense_category_line_ids.sorted(
            key=lambda line: (line.sequence, line.id)
        ).mapped("product_id")[:1]

    def _sync_primary_category_line(self):
        for rec in self:
            primary_line = rec.expense_category_line_ids.sorted(
                key=lambda line: (line.sequence, line.id)
            )[:1]
            if rec.hr_expense_product_id:
                if primary_line:
                    primary_line.product_id = rec.hr_expense_product_id
                else:
                    rec.expense_category_line_ids = [(0, 0, {
                        "sequence": 10,
                        "product_id": rec.hr_expense_product_id.id,
                    })]
            elif primary_line:
                primary_line.unlink()

    @api.model
    def _normalize_operating_detail_label(self, value):
        text = value or ""
        replacements = {
            "-": " ",
            "/": " ",
            "&": " ",
            ",": " ",
            ".": " ",
            "(": " ",
            ")": " ",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return " ".join(text.casefold().split())

    @api.model
    def _get_default_operating_catalog(self):
        return [dict(item) for item in OPERATING_EXPENSE_CONFIGS]

    @api.model
    def _get_default_operating_seed_map(self):
        return {item["seed_key"]: dict(item) for item in OPERATING_EXPENSE_CONFIGS}

    @api.model
    def _get_default_operating_other_seed_key(self):
        return "operating_other"

    @api.model
    def _get_default_operating_product(self):
        tax = self._get_default_operating_tax()
        product = self.env["product.product"].with_context(active_test=False).search(
            [("default_code", "=", "TENENET_OPERATING_EXPENSE"), ("can_be_expensed", "=", True)],
            limit=1,
        )
        if product:
            product.supplier_taxes_id = [Command.set(tax.ids)]
            return product
        return self.env["product.product"].create({
            "name": "Prevádzkový náklad",
            "default_code": "TENENET_OPERATING_EXPENSE",
            "type": "service",
            "can_be_expensed": True,
            "supplier_taxes_id": [Command.set(tax.ids)],
        })

    @api.model
    def _get_default_project_import_product(self):
        tax = self._get_default_operating_tax()
        product = self.env["product.product"].with_context(active_test=False).search(
            [("default_code", "=", "TENENET_PROJECT_EXPENSE_IMPORT"), ("can_be_expensed", "=", True)],
            limit=1,
        )
        if product:
            product.supplier_taxes_id = [Command.set(tax.ids)]
            return product
        return self.env["product.product"].create({
            "name": "Projektový náklad",
            "default_code": "TENENET_PROJECT_EXPENSE_IMPORT",
            "type": "service",
            "can_be_expensed": True,
            "supplier_taxes_id": [Command.set(tax.ids)],
        })

    @api.model
    def _get_default_operating_tax(self):
        company = self.env.company
        Tax = self.env["account.tax"].with_context(active_test=False)
        tax = Tax.search([
            ("company_id", "=", company.id),
            ("type_tax_use", "=", "purchase"),
            ("amount_type", "=", "percent"),
            ("amount", "=", 23.0),
        ], limit=1)
        if tax:
            if not tax.price_include:
                tax.price_include = True
            return tax
        existing_name = Tax.search([
            ("company_id", "=", company.id),
            ("name", "=", "23 %"),
        ], limit=1)
        tax_name = "23 % (nákup)" if existing_name else "23 %"
        return Tax.create({
            "name": tax_name,
            "type_tax_use": "purchase",
            "amount_type": "percent",
            "amount": 23.0,
            "price_include": True,
            "company_id": company.id,
        })

    @api.model
    def _load_default_operating_seed_data(self):
        product = self._get_default_operating_product()
        existing_by_seed = {
            record.seed_key: record
            for record in self.with_context(active_test=False).search([
                ("seed_key", "!=", False),
            ])
        }
        for item in self._get_default_operating_catalog():
            values = {
                "name": item["name"],
                "sequence": item["sequence"],
                "tenenet_usage": item["tenenet_usage"],
                "cashflow_row_key": item["cashflow_row_key"],
                "cashflow_row_label": item["cashflow_row_label"],
                "admin_pl_row_key": item["admin_pl_row_key"],
                "admin_pl_row_label": item["admin_pl_row_label"],
                "seed_key": item["seed_key"],
                "active": True,
            }
            record = existing_by_seed.get(item["seed_key"])
            if record:
                values["hr_expense_product_id"] = record.hr_expense_product_id.id or product.id
                record.write(values)
            else:
                values["hr_expense_product_id"] = product.id
                self.create(values)

    @api.model
    def _match_operating_seed_key_for_detail_label(self, detail_label):
        normalized = self._normalize_operating_detail_label(detail_label)
        if not normalized:
            return self._get_default_operating_other_seed_key()
        if normalized in OPERATING_DETAIL_LABEL_ALIASES:
            return OPERATING_DETAIL_LABEL_ALIASES[normalized]
        for alias, seed_key in OPERATING_DETAIL_LABEL_ALIASES.items():
            if alias in normalized:
                return seed_key
        return self._get_default_operating_other_seed_key()

    @api.model
    def _find_or_create_operating_type_for_detail_label(self, detail_label):
        self._load_default_operating_seed_data()
        seed_key = self._match_operating_seed_key_for_detail_label(detail_label)
        record = self.with_context(active_test=False).search([("seed_key", "=", seed_key)], limit=1)
        if record:
            return record
        catalog = self._get_default_operating_seed_map()
        values = dict(catalog[seed_key])
        values["hr_expense_product_id"] = self._get_default_operating_product().id
        return self.create(values)

    @api.model
    def _find_or_create_project_cashflow_import_type(self, row_key, row_label):
        record = self.with_context(active_test=False).search([
            ("cashflow_row_key", "=", row_key),
            ("tenenet_usage", "in", ["project", "both"]),
        ], limit=1)
        if record:
            updates = {}
            if row_label and record.cashflow_row_label != row_label:
                updates["cashflow_row_label"] = row_label
            if not record.hr_expense_product_id:
                updates["hr_expense_product_id"] = self._get_default_project_import_product().id
            if updates:
                record.write(updates)
            return record

        return self.create({
            "name": row_label,
            "description": "Importovaný projektový náklad z cashflow workbooku.",
            "tenenet_usage": "project",
            "cashflow_row_key": row_key,
            "cashflow_row_label": row_label,
            "hr_expense_product_id": self._get_default_project_import_product().id,
        })
