import csv
import math
from dataclasses import dataclass
from pathlib import Path

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import ValidationError


REGIME_SELECTION = [
    ("law_553_public_interest", "553/2003 - verejný záujem"),
    ("law_553_pedagogical", "553/2003 - pedagogickí a odborní zamestnanci"),
    ("healthcare", "578/2004 - zdravotnícki pracovníci"),
]

HEALTHCARE_LANE_SELECTION = [
    ("professional", "Odborné"),
    ("certified", "CPČ"),
    ("specialized", "ŠČ"),
    ("advanced_practice", "Pokročilá prax"),
]

HEALTHCARE_PROFESSION_SELECTION = [
    ("physician", "Lekár"),
    ("psychologist", "Psychológ"),
    ("logopedist", "Logopéd"),
    ("therapeutic_pedagogue", "Liečebný pedagóg"),
    ("nurse", "Sestra"),
    ("physiotherapist", "Fyzioterapeut"),
]

PROGRAM_REGIME_BY_CODE = {
    "VCI": "law_553_public_interest",
    "SPODASK": "law_553_public_interest",
    "NAS_A_VAZ": "law_553_public_interest",
    "SSP": "law_553_public_interest",
    "APZ": "law_553_public_interest",
    "ZDRAV_ZNEV": "law_553_public_interest",
    "KC": "law_553_public_interest",
    "SCPP": "law_553_pedagogical",
    "SCPAP": "law_553_pedagogical",
    "AKP_DETI": "healthcare",
    "AKP_DOSP": "healthcare",
    "AKP_SHARED": "healthcare",
    "PSC_SC": "healthcare",
    "PSC_KE": "healthcare",
    "PSC_BB": "healthcare",
    "AVL": "healthcare",
    "AP": "healthcare",
    "PS": "healthcare",
}


def _as_float(value):
    if value in (None, "", False):
        return False
    if isinstance(value, (int, float)):
        return float(value)
    normalized = str(value).strip().replace(" ", "").replace(",", ".")
    return float(normalized) if normalized else False


def _normalize_key(value):
    return (value or "").strip().casefold()


@dataclass
class WageResolution:
    job: models.Model
    requested_program: models.Model
    effective_program: models.Model
    regime: str
    mapping: models.Model
    override: models.Model
    table: models.Model
    line: models.Model
    amount: float
    issue: str | None = None


class TenenetProgram(models.Model):
    _inherit = "tenenet.program"

    wage_regime = fields.Selection(
        selection=REGIME_SELECTION,
        string="Zákonný mzdový režim",
        help="Určuje právny režim, podľa ktorého sa počíta odporúčaná zákonná mzda pre program.",
    )

    @api.model
    def _sync_default_wage_regimes(self):
        for program in self.search([]):
            regime = PROGRAM_REGIME_BY_CODE.get(program.code)
            if program.wage_regime != regime:
                program.wage_regime = regime


class HrJob(models.Model):
    _inherit = "hr.job"

    is_tenenet_admin_management = fields.Boolean(
        string="Administratíva/manažment TENENET",
        help="Zamestnanci s touto hlavnou alebo vedľajšou pozíciou patria v P&L do mzdových nákladov administratívy.",
    )
    legal_wage_mapping_ids = fields.One2many(
        "tenenet.hr.job.legal.wage.map",
        "job_id",
        string="Právne mzdové mapovania",
    )


class TenenetWageTable(models.Model):
    _name = "tenenet.wage.table"
    _description = "Právna mzdová tabuľka"
    _order = "year desc, regime, name"

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    year = fields.Integer(required=True)
    regime = fields.Selection(selection=REGIME_SELECTION, required=True)
    source_name = fields.Char(required=True)
    source_url = fields.Char()
    valid_from = fields.Date(required=True)
    valid_to = fields.Date()
    active = fields.Boolean(default=True)
    line_count = fields.Integer(
        string="Počet riadkov",
        compute="_compute_line_count",
    )
    line_ids = fields.One2many(
        "tenenet.wage.table.line",
        "table_id",
        string="Riadky tabuľky",
    )

    _code_unique = models.Constraint("UNIQUE(code)", "Kód mzdovej tabuľky musí byť jedinečný.")

    @api.depends("line_ids")
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    @api.model
    def _seed_directory(self):
        directory = Path(__file__).resolve().parents[1] / "data" / "wage"
        if not directory.is_dir():
            raise ValidationError("Chýba adresár s mzdovými seed dátami modulu.")
        return directory

    @api.model
    def _seed_path(self, filename):
        return self._seed_directory() / filename

    @api.model
    def _load_default_wage_seed_data(self):
        self.env["tenenet.program"]._sync_default_wage_regimes()
        self._load_public_interest_seed()
        self._load_pedagogical_seed()
        self._load_healthcare_seed()
        self.env["tenenet.hr.job.legal.wage.map"]._load_default_seed_data()

    @api.model
    def _cleanup_legacy_salary_guidance_artifacts(self):
        xmlids = [
            "tenenet_projects.view_hr_job_form_tenenet_legal_wage",
            "tenenet_projects.view_hr_job_form_tenenet",
            "tenenet_projects.access_tenenet_hr_job_salary_range_hr_user",
            "tenenet_projects.access_tenenet_hr_job_salary_range_hr_manager",
        ]
        model_data = self.env["ir.model.data"].sudo()
        for xmlid in xmlids:
            module, name = xmlid.split(".", 1)
            data = model_data.search([("module", "=", module), ("name", "=", name)], limit=1)
            if not data:
                continue
            if data.model in self.env:
                self.env[data.model].sudo().browse(data.res_id).exists().unlink()
            data.unlink()

        model_data.search([
            ("module", "=", "tenenet_projects"),
            ("model", "=", "ir.model"),
            ("name", "=", "model_tenenet_hr_job_salary_range"),
        ]).unlink()

        self.env.cr.execute(
            """
            DELETE FROM ir_model_fields
            WHERE model IN ('hr.job', 'hr.employee')
              AND name IN ('salary_range_ids', 'salary_range_count', 'matched_salary_range_ids')
            """
        )
        self.env.cr.execute(
            """
            DELETE FROM ir_model
            WHERE model = 'tenenet.hr.job.salary.range'
            """
        )
        self.env.cr.execute("DROP TABLE IF EXISTS tenenet_hr_job_salary_range CASCADE")

    @api.model
    def _upsert_seed_table(self, values, lines):
        table = self.search([("code", "=", values["code"])], limit=1)
        if table:
            table.write(values)
        else:
            table = self.create(values)
        table.line_ids.unlink()
        for line_vals in lines:
            line_vals["table_id"] = table.id
            self.env["tenenet.wage.table.line"].create(line_vals)
        return table

    @api.model
    def _load_public_interest_seed(self):
        path = self._seed_path("public_interest_2026_matrix.csv")
        lines = []
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                sequence = int(row["step"])
                experience_from = _as_float(row["experience_from"]) or 0.0
                experience_to = _as_float(row["experience_to"])
                for pay_class in range(1, 12):
                    amount = _as_float(row[f"class_{pay_class}"])
                    lines.append({
                        "sequence": sequence,
                        "pay_class": pay_class,
                        "experience_years_from": experience_from,
                        "experience_years_to": experience_to,
                        "amount": amount,
                    })
        self._upsert_seed_table(
            {
                "name": "553/2003 - Príloha č. 3 (2026)",
                "code": "law_553_public_interest_2026",
                "year": 2026,
                "regime": "law_553_public_interest",
                "source_name": "Zákon 553/2003 Z. z., príloha č. 3",
                "source_url": "https://static.slov-lex.sk/pdf/SK/ZZ/2003/553/ZZ_2003_553_20260101.pdf",
                "valid_from": fields.Date.to_date("2026-01-01"),
                "valid_to": False,
            },
            lines,
        )

    @api.model
    def _load_pedagogical_seed(self):
        path = self._seed_path("pedagogical_2026.csv")
        lines = []
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader, start=1):
                lines.append({
                    "sequence": index,
                    "pay_class": int(row["pay_class"]),
                    "work_class": int(row["work_class"]),
                    "amount": _as_float(row["amount"]),
                    "evaluation_bonus": _as_float(row["evaluation_bonus"]) or 0.0,
                })
        self._upsert_seed_table(
            {
                "name": "553/2003 - Príloha č. 4 (2026)",
                "code": "law_553_pedagogical_2026",
                "year": 2026,
                "regime": "law_553_pedagogical",
                "source_name": "Zákon 553/2003 Z. z., príloha č. 4",
                "source_url": "https://static.slov-lex.sk/pdf/SK/ZZ/2003/553/ZZ_2003_553_20260101.pdf",
                "valid_from": fields.Date.to_date("2026-01-01"),
                "valid_to": False,
            },
            lines,
        )

    @api.model
    def _load_healthcare_seed(self):
        path = self._seed_path("healthcare_2026_summary.csv")
        lines = []
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            sequence = 1
            for row in reader:
                base_amount = _as_float(row["base_amount"]) or 0.0
                increment = _as_float(row["annual_increment"]) or 0.0
                max_years = int(row["max_years"] or 0)
                for years in range(max_years + 1):
                    lines.append({
                        "sequence": sequence,
                        "healthcare_profession_code": row["profession_code"],
                        "qualification_lane": row["qualification_lane"],
                        "experience_years_from": years,
                        "experience_years_to": years,
                        "amount": round(base_amount + (increment * years), 2),
                    })
                    sequence += 1
        self._upsert_seed_table(
            {
                "name": "578/2004 - zdravotnícke povolania (2026)",
                "code": "healthcare_2026",
                "year": 2026,
                "regime": "healthcare",
                "source_name": "MZ SR - Základné platy zdravotníkov 2026",
                "source_url": "https://www.health.gov.sk/Zdroje?/Sources/clanky/platy-1-2026/sumar.pdf",
                "valid_from": fields.Date.to_date("2026-01-01"),
                "valid_to": False,
            },
            lines,
        )

    @api.model
    def _get_active_table(self, regime, on_date=None):
        effective_date = fields.Date.to_date(on_date or fields.Date.context_today(self))
        domain = [
            ("regime", "=", regime),
            ("active", "=", True),
            ("valid_from", "<=", effective_date),
            "|",
            ("valid_to", "=", False),
            ("valid_to", ">=", effective_date),
        ]
        table = self.search(domain, order="year desc, id desc", limit=1)
        if table:
            return table
        return self.search([("regime", "=", regime), ("active", "=", True)], order="year desc, id desc", limit=1)

    def _resolve_line(self, *, pay_class=None, work_class=None, profession_code=None, qualification_lane=None, experience_years=0.0):
        self.ensure_one()
        lines = self.line_ids
        if self.regime == "law_553_public_interest":
            lines = lines.filtered(lambda rec: rec.pay_class == pay_class)
            return lines.filtered(
                lambda rec: (rec.experience_years_from or 0.0) <= experience_years + 1e-9
                and (rec.experience_years_to in (False, None) or experience_years <= rec.experience_years_to + 1e-9)
            ).sorted(
                lambda rec: (rec.experience_years_from or 0.0, rec.sequence, rec.id),
                reverse=True,
            )[:1]
        if self.regime == "law_553_pedagogical":
            return lines.filtered(lambda rec: rec.pay_class == pay_class and rec.work_class == work_class)[:1]
        lines = lines.filtered(
            lambda rec: rec.healthcare_profession_code == profession_code
            and rec.qualification_lane == qualification_lane
        )
        rounded_years = max(0, min(30, math.floor(experience_years or 0.0)))
        return lines.filtered(lambda rec: (rec.experience_years_from or 0.0) == rounded_years)[:1]


class TenenetWageTableLine(models.Model):
    _name = "tenenet.wage.table.line"
    _description = "Riadok právnej mzdovej tabuľky"
    _order = "table_id, sequence, pay_class, work_class, qualification_lane, experience_years_from, id"

    sequence = fields.Integer(default=10)
    table_id = fields.Many2one(
        "tenenet.wage.table",
        required=True,
        ondelete="cascade",
        index=True,
    )
    table_year = fields.Integer(related="table_id.year", store=True, readonly=True)
    table_active = fields.Boolean(related="table_id.active", store=True, readonly=True)
    regime = fields.Selection(related="table_id.regime", store=True, readonly=True)
    pay_class = fields.Integer(string="Platová trieda")
    work_class = fields.Integer(string="Pracovná trieda")
    healthcare_profession_code = fields.Selection(
        selection=HEALTHCARE_PROFESSION_SELECTION,
        string="Zdravotnícka profesia",
    )
    qualification_lane = fields.Selection(
        selection=HEALTHCARE_LANE_SELECTION,
        string="Kvalifikačná línia",
    )
    experience_years_from = fields.Float(string="Praxe od", digits=(10, 2), default=0.0)
    experience_years_to = fields.Float(string="Praxe do", digits=(10, 2))
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
        required=True,
    )
    amount = fields.Monetary(string="Mesačná suma", currency_field="currency_id", required=True)
    evaluation_bonus = fields.Monetary(
        string="Príplatok za hodnotenie",
        currency_field="currency_id",
        help="Používa sa pre pedagogických a odborných zamestnancov.",
    )
    display_name = fields.Char(compute="_compute_display_name")

    @api.depends(
        "table_id.name",
        "pay_class",
        "work_class",
        "healthcare_profession_code",
        "qualification_lane",
        "experience_years_from",
        "experience_years_to",
    )
    def _compute_display_name(self):
        profession_labels = dict(HEALTHCARE_PROFESSION_SELECTION)
        lane_labels = dict(HEALTHCARE_LANE_SELECTION)
        for record in self:
            parts = [record.table_id.name or "-"]
            if record.pay_class:
                parts.append(f"PT {record.pay_class}")
            if record.work_class:
                parts.append(f"PrT {record.work_class}")
            if record.healthcare_profession_code:
                parts.append(profession_labels.get(record.healthcare_profession_code, record.healthcare_profession_code))
            if record.qualification_lane:
                parts.append(lane_labels.get(record.qualification_lane, record.qualification_lane))
            if record.experience_years_to not in (False, None):
                parts.append(f"do {record.experience_years_to:g} r.")
            elif record.experience_years_from:
                parts.append(f"od {record.experience_years_from:g} r.")
            record.display_name = " / ".join(parts)


class TenenetHrJobLegalWageMap(models.Model):
    _name = "tenenet.hr.job.legal.wage.map"
    _description = "Právne mzdové mapovanie pozície"
    _order = "job_id, regime, id"

    seed_key = fields.Char(index=True, copy=False)
    active = fields.Boolean(default=True)
    job_id = fields.Many2one("hr.job", string="Pozícia", required=True, ondelete="cascade")
    regime = fields.Selection(selection=REGIME_SELECTION, required=True)
    pay_class = fields.Integer(string="Platová trieda")
    work_class = fields.Integer(string="Pracovná trieda")
    healthcare_profession_code = fields.Selection(
        selection=HEALTHCARE_PROFESSION_SELECTION,
        string="Zdravotnícka profesia",
    )
    qualification_lane = fields.Selection(
        selection=HEALTHCARE_LANE_SELECTION,
        string="Kvalifikačná línia",
    )
    classification_summary = fields.Char(
        string="Zaradenie",
        compute="_compute_classification_summary",
        store=True,
    )
    notes = fields.Text(string="Poznámka")
    display_name = fields.Char(compute="_compute_display_name")

    _job_regime_unique = models.Constraint(
        "UNIQUE(job_id, regime)",
        "Pre jednu pozíciu môže existovať len jedno aktívne mapovanie v danom právnom režime.",
    )

    @api.depends("job_id.name", "regime", "classification_summary")
    def _compute_display_name(self):
        regime_labels = dict(REGIME_SELECTION)
        for record in self:
            parts = [record.job_id.display_name or "-", regime_labels.get(record.regime, record.regime)]
            if record.classification_summary:
                parts.append(record.classification_summary)
            record.display_name = " / ".join(parts)

    @api.depends("regime", "pay_class", "work_class", "healthcare_profession_code", "qualification_lane")
    def _compute_classification_summary(self):
        profession_labels = dict(HEALTHCARE_PROFESSION_SELECTION)
        lane_labels = dict(HEALTHCARE_LANE_SELECTION)
        for record in self:
            parts = []
            if record.regime == "law_553_public_interest" and record.pay_class:
                parts.append(f"PT {record.pay_class}")
            elif record.regime == "law_553_pedagogical":
                if record.pay_class:
                    parts.append(f"PT {record.pay_class}")
                if record.work_class:
                    parts.append(f"PrT {record.work_class}")
            elif record.regime == "healthcare":
                if record.healthcare_profession_code:
                    parts.append(
                        profession_labels.get(record.healthcare_profession_code, record.healthcare_profession_code)
                    )
                if record.qualification_lane:
                    parts.append(lane_labels.get(record.qualification_lane, record.qualification_lane))
            record.classification_summary = " / ".join(parts)

    @api.onchange("regime")
    def _onchange_regime(self):
        for record in self:
            if record.regime == "law_553_public_interest":
                record.work_class = False
                record.healthcare_profession_code = False
                record.qualification_lane = False
            elif record.regime == "law_553_pedagogical":
                record.healthcare_profession_code = False
                record.qualification_lane = False
            elif record.regime == "healthcare":
                record.pay_class = False
                record.work_class = False

    @api.constrains("regime", "pay_class", "work_class", "healthcare_profession_code")
    def _check_required_classification(self):
        for record in self:
            if record.regime == "law_553_public_interest" and not record.pay_class:
                raise ValidationError("Pri režime 553/2003 - verejný záujem musí byť vyplnená platová trieda.")
            if record.regime == "law_553_pedagogical" and (not record.pay_class or not record.work_class):
                raise ValidationError("Pri pedagogickom režime musia byť vyplnené platová trieda aj pracovná trieda.")
            if record.regime == "healthcare" and not record.healthcare_profession_code:
                raise ValidationError("Pri zdravotníckom režime musí byť vyplnená zdravotnícka profesia.")

    @api.model
    def _load_default_seed_data(self):
        path = self.env["tenenet.wage.table"]._seed_path("job_regime_mapping_seeds.csv")
        jobs_by_name = {
            _normalize_key(job.name): job
            for job in self.env["hr.job"].search([])
        }
        with open(path, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                job = jobs_by_name.get(_normalize_key(row["job_name"]))
                if not job:
                    continue
                values = {
                    "job_id": job.id,
                    "regime": row["regime"],
                    "pay_class": int(row["pay_class"]) if row.get("pay_class") else False,
                    "work_class": int(row["work_class"]) if row.get("work_class") else False,
                    "healthcare_profession_code": row.get("healthcare_profession_code") or False,
                    "qualification_lane": row.get("qualification_lane") or False,
                    "notes": row.get("notes") or False,
                    "active": True,
                }
                record = self.search([("seed_key", "=", row["seed_key"])], limit=1)
                if record:
                    record.write(values)
                else:
                    values["seed_key"] = row["seed_key"]
                    self.create(values)


class TenenetEmployeeWageOverride(models.Model):
    _name = "tenenet.employee.wage.override"
    _description = "Override právneho mzdového odporúčania"
    _order = "employee_id, date_start desc, id desc"

    active = fields.Boolean(default=True)
    employee_id = fields.Many2one("hr.employee", string="Zamestnanec", required=True, ondelete="cascade")
    job_id = fields.Many2one("hr.job", string="Len pre pozíciu", ondelete="set null")
    program_id = fields.Many2one("tenenet.program", string="Len pre program", ondelete="set null")
    override_program_id = fields.Many2one("tenenet.program", string="Nahradiť program", ondelete="set null")
    date_start = fields.Date(string="Platí od")
    date_end = fields.Date(string="Platí do")
    effective_regime = fields.Selection(
        selection=REGIME_SELECTION,
        string="Použitý režim",
        compute="_compute_effective_regime",
        store=True,
    )
    pay_class = fields.Integer(string="Platová trieda")
    work_class = fields.Integer(string="Pracovná trieda")
    healthcare_profession_code = fields.Selection(
        selection=HEALTHCARE_PROFESSION_SELECTION,
        string="Zdravotnícka profesia",
    )
    qualification_lane = fields.Selection(
        selection=HEALTHCARE_LANE_SELECTION,
        string="Kvalifikačná línia",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Mena",
        default=lambda self: self.env.ref("base.EUR"),
        required=True,
    )
    amount_override = fields.Monetary(
        string="Prepísaná odporúčaná suma",
        currency_field="currency_id",
        help="Ak je vyplnené, použije sa namiesto sumy vypočítanej z tabuľky.",
    )
    scope_summary = fields.Char(
        string="Rozsah",
        compute="_compute_scope_summary",
        store=True,
    )
    classification_summary = fields.Char(
        string="Prepísané zaradenie",
        compute="_compute_classification_summary",
        store=True,
    )
    notes = fields.Text(string="Zdôvodnenie / poznámka")

    @api.depends(
        "override_program_id.wage_regime",
        "program_id.wage_regime",
        "employee_id.wage_program_override_id.wage_regime",
    )
    def _compute_effective_regime(self):
        for record in self:
            record.effective_regime = (
                record.override_program_id.wage_regime
                or record.program_id.wage_regime
                or record.employee_id.wage_program_override_id.wage_regime
                or False
            )

    @api.depends("job_id.name", "program_id.name", "override_program_id.name", "date_start", "date_end")
    def _compute_scope_summary(self):
        for record in self:
            parts = []
            if record.job_id:
                parts.append(f"pozícia: {record.job_id.display_name}")
            else:
                parts.append("všetky pozície")
            if record.program_id:
                parts.append(f"program: {record.program_id.display_name}")
            else:
                parts.append("všetky programy")
            if record.override_program_id:
                parts.append(f"nahradiť program na: {record.override_program_id.display_name}")
            if record.date_start or record.date_end:
                date_bits = ["platnosť"]
                if record.date_start:
                    date_bits.append(f"od {record.date_start}")
                if record.date_end:
                    date_bits.append(f"do {record.date_end}")
                parts.append(" ".join(date_bits))
            record.scope_summary = " | ".join(parts)

    @api.depends("effective_regime", "pay_class", "work_class", "healthcare_profession_code", "qualification_lane", "amount_override")
    def _compute_classification_summary(self):
        profession_labels = dict(HEALTHCARE_PROFESSION_SELECTION)
        lane_labels = dict(HEALTHCARE_LANE_SELECTION)
        for record in self:
            parts = []
            if record.effective_regime == "law_553_public_interest" and record.pay_class:
                parts.append(f"PT {record.pay_class}")
            elif record.effective_regime == "law_553_pedagogical":
                if record.pay_class:
                    parts.append(f"PT {record.pay_class}")
                if record.work_class:
                    parts.append(f"PrT {record.work_class}")
            elif record.effective_regime == "healthcare":
                if record.healthcare_profession_code:
                    parts.append(
                        profession_labels.get(record.healthcare_profession_code, record.healthcare_profession_code)
                    )
                if record.qualification_lane:
                    parts.append(lane_labels.get(record.qualification_lane, record.qualification_lane))
            if record.amount_override:
                parts.append(f"suma {record.amount_override:,.2f} EUR".replace(",", " "))
            record.classification_summary = " / ".join(parts)

    @api.constrains("date_start", "date_end", "amount_override")
    def _check_date_range(self):
        for record in self:
            if record.date_start and record.date_end and record.date_end < record.date_start:
                raise ValidationError("Dátum do nemôže byť skorší ako dátum od.")
            if record.amount_override and record.amount_override < 0:
                raise ValidationError("Prepísaná suma nemôže byť záporná.")


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    wage_program_override_id = fields.Many2one(
        "tenenet.program",
        string="Mzdový program override",
        ondelete="set null",
        help="Ak je vyplnený, právne mzdové usmernenie sa vypočíta len podľa tohto programu namiesto aktívnych priradení.",
    )
    wage_override_ids = fields.One2many(
        "tenenet.employee.wage.override",
        "employee_id",
        string="Override mzdového usmernenia",
    )
    salary_guidance_context_html = fields.Html(
        string="Kontext právneho mzdového usmernenia",
        compute="_compute_salary_guidance_context_html",
        compute_sudo=True,
        sanitize=False,
    )

    def _get_salary_guidance_context(self):
        self.ensure_one()
        programs = self._get_salary_guidance_programs()
        jobs = self._get_job_sequence()
        source = "manual" if self.wage_program_override_id else "assignments"
        return {
            "programs": programs,
            "jobs": jobs,
            "source": source,
            "override_count": len(self.wage_override_ids.filtered("active")),
        }

    @api.depends(
        "job_id",
        "job_id.name",
        "additional_job_ids",
        "additional_job_ids.name",
        "wage_program_override_id",
        "wage_program_override_id.name",
        "assignment_ids",
        "assignment_ids.active",
        "assignment_ids.state",
        "assignment_ids.program_id",
        "assignment_ids.program_id.name",
        "assignment_ids.project_id",
        "assignment_ids.project_id.reporting_program_id",
        "assignment_ids.project_id.reporting_program_id.name",
        "wage_override_ids",
        "wage_override_ids.active",
    )
    def _compute_salary_guidance_context_html(self):
        for employee in self:
            context = employee._get_salary_guidance_context()
            current_target_ccp = employee._get_effective_monthly_gross_salary_target()
            current_target_hm = employee._get_effective_monthly_gross_salary_target_hm()
            metrics = employee._get_month_workday_metrics(employee._get_target_period())
            source_label = "Manuálne zvolený program" if context["source"] == "manual" else "Aktívne priradenia"
            program_items = "".join(
                f"<span class='o_tenenet_employee_chip'>{escape(program.display_name)}</span>"
                for program in context["programs"]
            ) or "<span class='text-muted'>Žiadny program</span>"
            job_items = "".join(
                f"<span class='o_tenenet_employee_chip'>{escape(job.display_name)}</span>"
                for job in context["jobs"]
            ) or "<span class='text-muted'>Žiadna mapovaná profesia</span>"
            override_label = (
                f"{context['override_count']} aktívnych výnimiek"
                if context["override_count"]
                else "Bez aktívnych výnimiek"
            )
            employee.salary_guidance_context_html = Markup(
                """
                <div class="o_tenenet_salary_context_grid">
                    <div class="o_tenenet_salary_context_card">
                        <div class="o_tenenet_salary_context_label">Zdroj programu</div>
                        <div class="o_tenenet_salary_context_value">%s</div>
                    </div>
                    <div class="o_tenenet_salary_context_card">
                        <div class="o_tenenet_salary_context_label">Použité programy</div>
                        <div class="o_tenenet_employee_chip_row">%s</div>
                    </div>
                    <div class="o_tenenet_salary_context_card">
                        <div class="o_tenenet_salary_context_label">Použité profesie</div>
                        <div class="o_tenenet_employee_chip_row">%s</div>
                    </div>
                    <div class="o_tenenet_salary_context_card">
                        <div class="o_tenenet_salary_context_label">Výnimky</div>
                        <div class="o_tenenet_salary_context_value">%s</div>
                    </div>
                    <div class="o_tenenet_salary_context_card">
                        <div class="o_tenenet_salary_context_label">Base cieľ bez sviatkov</div>
                        <div class="o_tenenet_salary_context_value">%s CCP / %s HM</div>
                    </div>
                    <div class="o_tenenet_salary_context_card">
                        <div class="o_tenenet_salary_context_label">Aktuálny mesiac po sviatkoch</div>
                        <div class="o_tenenet_salary_context_value">%s CCP / %s HM</div>
                    </div>
                    <div class="o_tenenet_salary_context_card">
                        <div class="o_tenenet_salary_context_label">Pracovné dni</div>
                        <div class="o_tenenet_salary_context_value">%s dní, sviatky %s, po sviatkoch %s</div>
                    </div>
                </div>
                """
            ) % (
                escape(source_label),
                Markup(program_items),
                Markup(job_items),
                escape(override_label),
                escape(f"{employee.monthly_gross_salary_target:,.2f}".replace(",", " ")),
                escape(f"{employee.monthly_gross_salary_target_hm:,.2f}".replace(",", " ")),
                escape(f"{current_target_ccp:,.2f}".replace(",", " ")),
                escape(f"{current_target_hm:,.2f}".replace(",", " ")),
                escape(metrics["base_workdays"]),
                escape(metrics["holiday_workdays"]),
                escape(metrics["effective_workdays"]),
            )

    @api.depends(
        "job_id",
        "job_id.name",
        "additional_job_ids",
        "additional_job_ids.name",
        "experience_years_total",
        "monthly_gross_salary_target",
        "monthly_gross_salary_target_hm",
        "wage_program_override_id",
        "wage_program_override_id.name",
        "wage_program_override_id.wage_regime",
        "assignment_ids",
        "assignment_ids.active",
        "assignment_ids.state",
        "assignment_ids.program_id",
        "assignment_ids.program_id.name",
        "assignment_ids.program_id.wage_regime",
        "assignment_ids.project_id",
        "assignment_ids.project_id.reporting_program_id",
        "assignment_ids.project_id.reporting_program_id.name",
        "assignment_ids.project_id.reporting_program_id.wage_regime",
        "wage_override_ids",
        "wage_override_ids.active",
        "wage_override_ids.job_id",
        "wage_override_ids.program_id",
        "wage_override_ids.override_program_id",
        "wage_override_ids.date_start",
        "wage_override_ids.date_end",
        "wage_override_ids.pay_class",
        "wage_override_ids.work_class",
        "wage_override_ids.healthcare_profession_code",
        "wage_override_ids.qualification_lane",
        "wage_override_ids.amount_override",
        "wage_override_ids.notes",
    )
    def _compute_salary_guidance_html(self):
        regime_labels = dict(REGIME_SELECTION)
        profession_labels = dict(HEALTHCARE_PROFESSION_SELECTION)
        lane_labels = dict(HEALTHCARE_LANE_SELECTION)
        for employee in self:
            target_html = ""
            cards = []
            effective_target_ccp = employee._get_effective_monthly_gross_salary_target()
            effective_target_hm = employee._get_effective_monthly_gross_salary_target_hm()
            metrics = employee._get_month_workday_metrics(employee._get_target_period())
            if employee.monthly_gross_salary_target:
                target_html = (
                    "<div class='o_tenenet_salary_target'>Base mesačný cieľ CCP bez sviatkov: "
                    f"<strong>{escape(f'{employee.monthly_gross_salary_target:,.2f}'.replace(',', ' '))} EUR</strong>"
                    " / odvodený HM (brutto): "
                    f"<strong>{escape(f'{employee.monthly_gross_salary_target_hm:,.2f}'.replace(',', ' '))} EUR</strong></div>"
                    "<div class='o_tenenet_salary_target'>Aktuálny mesiac po sviatkoch: "
                    f"<strong>{escape(f'{effective_target_ccp:,.2f}'.replace(',', ' '))} EUR CCP</strong>"
                    " / "
                    f"<strong>{escape(f'{effective_target_hm:,.2f}'.replace(',', ' '))} EUR HM</strong>"
                    f" <span class='text-muted'>({metrics['base_workdays']} prac. dní, sviatky {metrics['holiday_workdays']}, po sviatkoch {metrics['effective_workdays']})</span></div>"
                )

            resolutions = employee._get_legal_wage_resolutions()
            if not resolutions:
                employee.salary_guidance_html = Markup(
                    "<div class='o_tenenet_salary_guidance'>%s<div class='o_tenenet_salary_empty_state'>Pre zamestnanca zatiaľ nie je dostupný právny mzdový kontext. Nastav mzdový program override alebo aktívne priradenie k programu so zvoleným zákonným režimom.</div></div>"
                ) % Markup(target_html)
                continue

            for resolution in resolutions:
                classification_bits = []
                if resolution.regime in ("law_553_public_interest", "law_553_pedagogical") and resolution.override.pay_class:
                    classification_bits.append(f"PT {resolution.override.pay_class}")
                elif resolution.mapping and resolution.mapping.pay_class:
                    classification_bits.append(f"PT {resolution.mapping.pay_class}")
                if resolution.regime == "law_553_pedagogical":
                    work_class = resolution.override.work_class or (resolution.mapping.work_class if resolution.mapping else False)
                    if work_class:
                        classification_bits.append(f"PrT {work_class}")
                if resolution.regime == "healthcare":
                    profession_code = resolution.override.healthcare_profession_code or (
                        resolution.mapping.healthcare_profession_code if resolution.mapping else False
                    )
                    lane_code = resolution.override.qualification_lane or (
                        resolution.mapping.qualification_lane if resolution.mapping else False
                    )
                    if profession_code:
                        classification_bits.append(profession_labels.get(profession_code, profession_code))
                    if lane_code:
                        classification_bits.append(lane_labels.get(lane_code, lane_code))

                source_link = ""
                if resolution.table and resolution.table.source_url:
                    source_link = (
                        f"<a href='{escape(resolution.table.source_url)}' target='_blank' rel='noreferrer'>{escape(resolution.table.source_name)}</a>"
                    )
                elif resolution.table:
                    source_link = escape(resolution.table.source_name)

                experience_label = ""
                if resolution.line:
                    if resolution.regime == "law_553_pedagogical":
                        experience_label = "Pedagogická tarifa bez pásma praxe"
                    elif resolution.line.experience_years_to not in (False, None) and resolution.line.experience_years_from:
                        experience_label = (
                            f"Praxe: {resolution.line.experience_years_from:g} - {resolution.line.experience_years_to:g} rokov"
                        )
                    elif resolution.line.experience_years_to not in (False, None):
                        experience_label = f"Praxe: do {resolution.line.experience_years_to:g} rokov"
                    elif resolution.line.experience_years_from:
                        experience_label = f"Praxe: od {resolution.line.experience_years_from:g} rokov"

                delta_html = ""
                if resolution.amount and effective_target_ccp:
                    delta = effective_target_hm - resolution.amount
                    if abs(delta) < 0.005:
                        delta_class = "is-match"
                        delta_text = "Aktuálny HM cieľ po sviatkoch je na úrovni odporúčania."
                    elif delta < 0:
                        delta_class = "is-below"
                        delta_text = f"Aktuálny HM cieľ po sviatkoch je nižší o {abs(delta):,.2f} EUR."
                    else:
                        delta_class = "is-above"
                        delta_text = f"Aktuálny HM cieľ po sviatkoch je vyšší o {abs(delta):,.2f} EUR."
                    delta_html = (
                        f"<div class='o_tenenet_salary_delta {delta_class}'>{escape(delta_text.replace(',', ' '))}</div>"
                    )

                note_html = ""
                if resolution.issue:
                    note_html += f"<div class='o_tenenet_salary_range_note o_tenenet_salary_issue'>{escape(resolution.issue)}</div>"
                if resolution.override and resolution.override.notes:
                    note_html += (
                        f"<div class='o_tenenet_salary_range_note'><strong>Override:</strong> {escape(resolution.override.notes)}</div>"
                    )
                elif resolution.mapping and resolution.mapping.notes:
                    note_html += f"<div class='o_tenenet_salary_range_note'>{escape(resolution.mapping.notes)}</div>"

                value_html = (
                    f"{escape(f'{resolution.amount:,.2f}'.replace(',', ' '))} EUR"
                    if resolution.amount
                    else "Bez vypočítanej sumy"
                )
                override_badge = (
                    "<span class='o_tenenet_employee_chip o_tenenet_employee_chip_warning'>Override</span>"
                    if resolution.override and (
                        resolution.override.amount_override
                        or resolution.override.pay_class
                        or resolution.override.work_class
                        or resolution.override.qualification_lane
                        or resolution.override.healthcare_profession_code
                        or resolution.override.override_program_id
                    )
                    else ""
                )
                program_name = resolution.effective_program.display_name or resolution.requested_program.display_name or "-"
                cards.append(
                    """
                    <div class="o_tenenet_salary_range_card o_tenenet_legal_wage_card">
                        <div class="o_tenenet_salary_range_header">
                            <div>
                                <div class="o_tenenet_salary_range_job">%s</div>
                                <div class="o_tenenet_salary_range_meta">Program: %s</div>
                            </div>
                            %s
                        </div>
                        <div class="o_tenenet_salary_range_value">%s</div>
                        <div class="o_tenenet_salary_range_meta"><strong>Režim:</strong> %s</div>
                        <div class="o_tenenet_salary_range_meta"><strong>Zaradenie:</strong> %s</div>
                        <div class="o_tenenet_salary_range_meta"><strong>Prax:</strong> %s</div>
                        <div class="o_tenenet_salary_range_meta"><strong>Zdroj:</strong> %s</div>
                        %s
                        %s
                    </div>
                    """
                    % (
                        escape(resolution.job.display_name or "-"),
                        escape(program_name),
                        Markup(override_badge),
                        escape(value_html),
                        escape(regime_labels.get(resolution.regime, resolution.regime) or "Chýba režim"),
                        escape(" / ".join(classification_bits) if classification_bits else "Chýba klasifikácia"),
                        escape(experience_label or f"{employee.experience_years_total:g} rokov"),
                        Markup(source_link) if source_link else "-",
                        Markup(delta_html),
                        Markup(note_html),
                    )
                )

            employee.salary_guidance_html = Markup(
                "<div class='o_tenenet_salary_guidance'>%s<div class='o_tenenet_salary_range_grid'>%s</div></div>"
            ) % (Markup(target_html), Markup("".join(cards)))

    def _get_salary_guidance_programs(self):
        self.ensure_one()
        if self.wage_program_override_id:
            return self.wage_program_override_id

        programs = self.env["tenenet.program"]
        for assignment in self.assignment_ids.filtered(lambda rec: rec.active and rec.state == "active"):
            program = assignment.program_id or assignment.project_id._get_effective_reporting_program()
            if program and program not in programs:
                programs |= program
        return programs

    def _match_wage_override(self, job, program, on_date):
        self.ensure_one()
        candidates = self.wage_override_ids.filtered(
            lambda rec: rec.active
            and (not rec.job_id or rec.job_id == job)
            and (not rec.program_id or rec.program_id == program)
            and (not rec.date_start or rec.date_start <= on_date)
            and (not rec.date_end or rec.date_end >= on_date)
        )
        if not candidates:
            return self.env["tenenet.employee.wage.override"]
        return candidates.sorted(
            key=lambda rec: (
                1 if rec.job_id else 0,
                1 if rec.program_id else 0,
                fields.Date.to_date(rec.date_start) if rec.date_start else fields.Date.to_date("1900-01-01"),
                rec.id,
            ),
            reverse=True,
        )[:1]

    def _get_legal_wage_resolutions(self):
        self.ensure_one()
        programs = self._get_salary_guidance_programs()
        if not programs:
            return []

        jobs = self._get_job_sequence()
        if not jobs:
            return [
                WageResolution(
                    job=self.env["hr.job"],
                    requested_program=programs[:1],
                    effective_program=programs[:1],
                    regime=programs[:1].wage_regime,
                    mapping=self.env["tenenet.hr.job.legal.wage.map"],
                    override=self.env["tenenet.employee.wage.override"],
                    table=self.env["tenenet.wage.table"],
                    line=self.env["tenenet.wage.table.line"],
                    amount=0.0,
                    issue="Chýba mapovaná profesia zamestnanca.",
                )
            ]

        today = fields.Date.context_today(self)
        mapping_model = self.env["tenenet.hr.job.legal.wage.map"]
        table_model = self.env["tenenet.wage.table"]
        results = []
        for program in programs:
            if not program.wage_regime:
                results.append(
                    WageResolution(
                        job=jobs[:1],
                        requested_program=program,
                        effective_program=program,
                        regime=False,
                        mapping=self.env["tenenet.hr.job.legal.wage.map"],
                        override=self.env["tenenet.employee.wage.override"],
                        table=self.env["tenenet.wage.table"],
                        line=self.env["tenenet.wage.table.line"],
                        amount=0.0,
                        issue="Program nemá nastavený zákonný mzdový režim.",
                    )
                )
                continue
            for job in jobs:
                override = self._match_wage_override(job, program, today)
                effective_program = override.override_program_id or program
                regime = effective_program.wage_regime or program.wage_regime
                if not regime:
                    results.append(
                        WageResolution(
                            job=job,
                            requested_program=program,
                            effective_program=effective_program,
                            regime=program.wage_regime,
                            mapping=self.env["tenenet.hr.job.legal.wage.map"],
                            override=override,
                            table=self.env["tenenet.wage.table"],
                            line=self.env["tenenet.wage.table.line"],
                            amount=override.amount_override or 0.0,
                            issue="Použitý program po override nemá nastavený zákonný mzdový režim.",
                        )
                    )
                    continue
                mapping = mapping_model.search([("job_id", "=", job.id), ("regime", "=", regime), ("active", "=", True)], limit=1)
                if not mapping and not override:
                    results.append(
                        WageResolution(
                            job=job,
                            requested_program=program,
                            effective_program=effective_program,
                            regime=regime,
                            mapping=mapping,
                            override=override,
                            table=table_model,
                            line=self.env["tenenet.wage.table.line"],
                            amount=0.0,
                            issue="Chýba mapovanie profesie na zákonnú klasifikáciu pre tento režim.",
                        )
                    )
                    continue

                pay_class = override.pay_class or (mapping.pay_class if mapping else False)
                work_class = override.work_class or (mapping.work_class if mapping else False)
                profession_code = override.healthcare_profession_code or (
                    mapping.healthcare_profession_code if mapping else False
                )
                qualification_lane = override.qualification_lane or (
                    mapping.qualification_lane if mapping else False
                )
                table = table_model._get_active_table(regime, on_date=today)
                if not table:
                    results.append(
                        WageResolution(
                            job=job,
                            requested_program=program,
                            effective_program=effective_program,
                            regime=regime,
                            mapping=mapping,
                            override=override,
                            table=table,
                            line=self.env["tenenet.wage.table.line"],
                            amount=override.amount_override or 0.0,
                            issue="Chýba aktívna právna tabuľka pre zvolený režim.",
                        )
                    )
                    continue

                line = table._resolve_line(
                    pay_class=pay_class,
                    work_class=work_class,
                    profession_code=profession_code,
                    qualification_lane=qualification_lane,
                    experience_years=self.experience_years_total or 0.0,
                )
                amount = override.amount_override or (line.amount if line else 0.0)
                issue = None
                if not amount:
                    issue = "Nepodarilo sa nájsť zodpovedajúci riadok v právnej tabuľke pre zadanú prax a klasifikáciu."
                results.append(
                    WageResolution(
                        job=job,
                        requested_program=program,
                        effective_program=effective_program,
                        regime=regime,
                        mapping=mapping,
                        override=override,
                        table=table,
                        line=line,
                        amount=amount,
                        issue=issue,
                    )
                )
        return results
