#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


SOURCE_HEADERS = [
    "Zamestnávateľ",
    "Titul",
    "Priezvisko a meno",
    "Program,do ktorého patria",
    "Pozícia podľa pracovnej zmluvy",
    "Pozícia",
    "Priamy nadriadený",
    "Lokácia",
    "Email",
    "TEL",
]

EMPLOYEE_HEADERS = [
    "id",
    "title_academic",
    "name",
    "job_id/id",
    "department_id/id",
    "parent_id/id",
    "address_id/id",
    "work_location",
    "main_site_name",
    "secondary_site_names",
    "organizational_unit_id/id",
    "contract_position",
    "work_email",
    "private_phone",
    "work_phone",
    "x_source_row",
    "x_raw_employer",
    "x_org_unit_code",
    "x_org_unit_mapping_status",
    "x_raw_program",
    "x_program_normalized",
    "x_wage_program_code",
    "x_raw_contract_position",
    "x_raw_position",
    "x_raw_manager",
    "x_location_unresolved",
    "x_import_action",
    "x_skip_reason",
    "x_normalization_status",
    "x_review_note",
]

JOB_HEADERS = ["id", "name", "x_department_code"]
DEPARTMENT_HEADERS = ["id", "name"]
LOCATION_HEADERS = ["id", "name", "type", "city", "country_id/id"]
PROGRAM_HEADERS = ["raw_program", "normalized_program_code", "normalized_program_name", "classification"]

INVALID_PHONE_MARKERS = {"", "x", "n/a", "na"}

PROGRAM_LOOKUP = {
    "AKP": ("AKP_SHARED", "AKP"),
    "AKP - DETI A MLADEZ": ("AKP_DETI", "AKP - deti a mládež"),
    "APZ": ("APZ", "APZ"),
    "APZ, EU CARE": ("APZ_EU_CARE", "APZ, EU CARE"),
    "AVL": ("AVL", "AVL"),
    "EU CARE": ("EU_CARE", "EU CARE"),
    "KC - KOMUNITNE CENTRA": ("KC", "Komunitné centrum"),
    "NAS A VAZENSTVO": ("NAS_A_VAZ", "Násilie a väzenstvo"),
    "PSC BB": ("PSC_BB", "Psychiatrické centrum Banská Bystrica"),
    "PSC KOSICE": ("PSC_KE", "Psychiatrické centrum Košice"),
    "PSC SENEC": ("PSC_SC", "Psychiatrické centrum Senec"),
    "SCPAP": ("SCPAP", "Súkromné centrum poradenstva a prevencie"),
    "SCPP": ("SCPP", "ŠCPP"),
    "SPODASK": ("SPODASK", "SPODaSK"),
    "STEM, GUIDE, SOCIALNE INOVACIE, APZ": ("SUPPORT_PROJECTS", "STEM, GUIDE, Sociálne inovácie, APZ"),
    "SVI": ("VCI", "Včasná intervencia"),
    "SSP": ("SSP", "Špecializované sociálne poradenstvo"),
}

PROGRAM_NOISE_RULES = [
    (re.compile(r"\bned[aá]va[ťt]\b", re.IGNORECASE), ("NO_IMPORT", "Poznámka - neimportovať")),
    (re.compile(r"u[žz]\s+je\s+na\s+webe", re.IGNORECASE), ("WEB_ONLY", "Poznámka - už je na webe")),
    (re.compile(r"kon[cč][ií].*2026", re.IGNORECASE), ("TRANSITION_NOTE", "Poznámka - prechod programu")),
    (re.compile(r"lep[sš]ie\s+pomenovanie.*SVI", re.IGNORECASE), ("VCI", "Včasná intervencia")),
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

ORG_UNIT_BY_EMPLOYER_RULES = [
    ("KALIA", ("KALIA", "KALIA")),
    ("SCPAP", ("SCPP", "SCPP")),
]

LOCATION_FIXES = {
    "Bratsislava": "Bratislava",
    "Galanta Trnava": "Galanta, Trnava",
    "Senec BSK, TTSK": "Senec, BSK, TTSK",
}

REGION_TOKEN_MAP = {
    "BSK": "Bratislavský samosprávny kraj",
    "TTSK": "Trnavský samosprávny kraj",
    "TSK": "Trnavský samosprávny kraj",
    "NSK": "Nitriansky samosprávny kraj",
    "ŽSK": "Žilinský samosprávny kraj",
    "ZSK": "Žilinský samosprávny kraj",
    "BBSK": "Banskobystrický samosprávny kraj",
    "PSK": "Prešovský samosprávny kraj",
    "KSK": "Košický samosprávny kraj",
}

JOB_SPECS = {
    "psycholog": ("Psychológ", "psychologia"),
    "specialny_pedagog": ("Špeciálny pedagóg", "specialna_pedagogika_terapie"),
    "liecebny_pedagog": ("Liečebný pedagóg", "specialna_pedagogika_terapie"),
    "socialny_pracovnik": ("Sociálny pracovník", "socialne_sluzby"),
    "komunitny_pracovnik": ("Komunitný pracovník", "komunitne_centrum"),
    "krizova_intervencia": ("Pracovník krízovej intervencie", "socialne_sluzby"),
    "zdravotna_sestra": ("Zdravotná sestra", "zdravotna_starostlivost"),
    "zdravotna_sestra_psychiatria": ("Zdravotná sestra v psychiatrii", "zdravotna_starostlivost"),
    "zdravotnicky_asistent": ("Zdravotnícky asistent", "zdravotna_starostlivost"),
    "lekar": ("Lekár", "zdravotna_starostlivost"),
    "psychiater": ("Psychiater", "zdravotna_starostlivost"),
    "logoped": ("Logopéd", "specialna_pedagogika_terapie"),
    "fyzioterapeut": ("Fyzioterapeut", "specialna_pedagogika_terapie"),
    "odborny_garant": ("Odborný garant", "manazment"),
    "odborny_riaditel": ("Odborný riaditeľ", "manazment"),
    "programovy_riaditel": ("Programový riaditeľ", "manazment"),
    "generalna_riaditelka": ("Generálna riaditeľka", "manazment"),
    "financna_riaditelka": ("Finančná riaditeľka", "manazment"),
    "financny_manazer": ("Finančný manažér", "prevadzka_a_podpora"),
    "projektovy_manazer": ("Projektový manažér", "prevadzka_a_podpora"),
    "prevadzkova_manazerka": ("Prevádzková manažérka", "prevadzka_a_podpora"),
    "personalista": ("Personalista", "prevadzka_a_podpora"),
    "mzdova_uctovnicka": ("Mzdová účtovníčka", "prevadzka_a_podpora"),
    "uctovnicka": ("Účtovníčka", "prevadzka_a_podpora"),
    "recepcna": ("Recepčná", "prevadzka_a_podpora"),
    "upratovacka": ("Upratovačka", "prevadzka_a_podpora"),
    "vyskumno_vyvojovy_pracovnik": ("Výskumný/vývojový pracovník", "prevadzka_a_podpora"),
    "socialna_inkluzia_pracovnik": ("Odborný pracovník pre sociálnu inklúziu a zamestnanosť", "socialne_sluzby"),
}

DEPARTMENTS = {
    "psychologia": "Psychológia",
    "socialne_sluzby": "Sociálne služby",
    "zdravotna_starostlivost": "Zdravotná starostlivosť",
    "specialna_pedagogika_terapie": "Špeciálna pedagogika a terapie",
    "komunitne_centrum": "Komunitné centrum",
    "prevadzka_a_podpora": "Prevádzka a podpora",
    "manazment": "Manažment",
}


@dataclass
class CleanedRow:
    source_row: int
    title: str
    name: str
    raw_employer: str
    org_unit_code: str
    org_unit_name: str
    org_unit_mapping_status: str
    raw_program: str
    raw_contract_position: str
    raw_position: str
    raw_manager: str
    raw_location: str
    raw_email: str
    raw_phone: str
    program_code: str
    program_name: str
    program_classification: str
    wage_program_code: str
    job_key: str
    job_name: str
    department_key: str
    department_name: str
    manager_name: str
    manager_employee_id: str
    work_location: str
    main_site_name: str
    secondary_site_names: list[str]
    location_unresolved: list[str]
    work_email: str
    mobile_phone: str
    work_phone: str
    import_action: str
    skip_reason: str
    status: str
    review_note: str
    employee_id: str
    missing_field_notes: list[str]
    manager_notes: list[str]
    location_notes: list[str]
    wage_mapping_notes: list[str]
    program_notes: list[str]


def normalize_text(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split())


def fold_text(value: str) -> str:
    text = normalize_text(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold()


def slugify(value: str) -> str:
    text = fold_text(value)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def employee_xmlid(name: str) -> str:
    return f"emp_{slugify(name)}"


def job_xmlid(job_key: str) -> str:
    return f"job_{job_key}"


def department_xmlid(department_key: str) -> str:
    return f"dept_{department_key}"


def location_xmlid(city: str) -> str:
    return f"loc_{slugify(city)}"


def organizational_unit_xmlid(unit_code: str) -> str:
    return f"tenenet_organizational_unit_{slugify(unit_code)}"


def sentence_case(value: str) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    return text[:1].upper() + text[1:].lower()


def classify_program(raw_program: str) -> tuple[str, str, str]:
    value = normalize_text(raw_program)
    if not value:
        return "", "", "empty"

    for pattern, result in PROGRAM_NOISE_RULES:
        if pattern.search(value):
            code, label = result
            if code == "VCI":
                return code, label, "normalized_from_note"
            return code, label, "note"

    lookup_key = fold_text(value).upper()
    if lookup_key in PROGRAM_LOOKUP:
        code, label = PROGRAM_LOOKUP[lookup_key]
        return code, label, "mapped"
    return "", "", "unmapped"


def map_organizational_unit(raw_employer: str) -> tuple[str, str, str]:
    employer = normalize_text(raw_employer)
    folded = fold_text(employer).upper()
    for needle, result in ORG_UNIT_BY_EMPLOYER_RULES:
        if needle in folded:
            return result[0], result[1], "mapped"
    if employer:
        return "TENENET_OZ", "TENENET o.z.", "default"
    return "TENENET_OZ", "TENENET o.z.", "default_blank"


def normalize_location(raw_location: str) -> str:
    value = normalize_text(raw_location)
    if not value:
        return ""
    return LOCATION_FIXES.get(value, value)


def split_locations(location: str) -> list[str]:
    normalized = normalize_location(location)
    if not normalized:
        return []
    return [part.strip() for part in normalized.split(",") if part.strip()]


def clean_email(raw_email: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    email = normalize_text(raw_email).lower()
    if not email:
        return "", notes
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", email):
        notes.append("neplatný e-mail sa neimportuje")
        return "", notes
    return email, notes


def format_phone(digits: str) -> str:
    if len(digits) == 9 and digits.startswith("9"):
        return f"+421 {digits[0:3]} {digits[3:6]} {digits[6:9]}"
    return digits


def format_landline(national_number: str) -> str:
    if len(national_number) == 8 and national_number.startswith("2"):
        return f"+421 2 {national_number[1:5]} {national_number[5:9]}"
    if len(national_number) == 9:
        return f"+421 {national_number[0:2]} {national_number[2:5]} {national_number[5:7]} {national_number[7:9]}"
    if len(national_number) == 8:
        return f"+421 {national_number[0:2]} {national_number[2:5]} {national_number[5:8]}"
    return f"+421 {national_number}"


def clean_phone(raw_phone: str) -> tuple[str, str, list[str]]:
    notes: list[str] = []
    phone = normalize_text(raw_phone)
    if not phone:
        return "", "", notes

    folded = fold_text(phone)
    if folded in INVALID_PHONE_MARKERS:
        notes.append("telefón sa neimportuje")
        return "", "", notes
    if "recepcie" in folded or "recepcia" in folded:
        notes.append("zdieľaná recepčná linka sa neimportuje")
        return "", "", notes

    digits = re.sub(r"\D", "", phone)
    if not digits:
        notes.append("telefón sa neimportuje")
        return "", "", notes

    if len(digits) == 9 and digits.startswith("9"):
        return format_phone(digits), "", notes
    if len(digits) == 9 and digits[0] in "2345678":
        return "", format_landline(digits), notes
    if len(digits) == 10 and digits.startswith("0"):
        return "", format_landline(digits[1:]), notes

    notes.append("telefón má neznámy formát a neimportuje sa")
    return "", "", notes


def resolve_job(raw_position: str, raw_contract_position: str, program_code: str) -> tuple[str, list[str]]:
    position = fold_text(raw_position)
    contract = fold_text(raw_contract_position)
    notes: list[str] = []

    if position == "psycholog" or contract == "psycholog":
        return "psycholog", notes
    if position == "specialny pedagog":
        return "specialny_pedagog", notes
    if position == "liecebny pedagog" or contract == "liecebny pedagog":
        notes.append("pozícia normalizovaná z preklepu na liečebný pedagóg")
        return "liecebny_pedagog", notes
    if position == "socialny pracovnik":
        return "socialny_pracovnik", notes
    if position in {"komunitny pracovnik", "pracovnik kc"} or contract in {"komunitny pracovnik", "pracovnik kc"}:
        if position != "komunitny pracovnik":
            notes.append("pozícia normalizovaná na komunitný pracovník")
        return "komunitny_pracovnik", notes
    if position == "pracovnik krizovej intervencie":
        return "krizova_intervencia", notes
    if position == "zdravotna sestra":
        return "zdravotna_sestra", notes
    if position == "zdravotna sestra v psychiatrii":
        return "zdravotna_sestra_psychiatria", notes
    if position == "zdravotnicky asistent":
        return "zdravotnicky_asistent", notes
    if position == "lekar" or contract == "vseobecny lekar pre dospelych":
        return "lekar", notes
    if position == "psychiater" or contract == "psychiater":
        return "psychiater", notes
    if position == "zdravotna sestra/zdravotny brat" or contract == "zdravotna sestra/zdravotny brat":
        notes.append("pozícia normalizovaná na zdravotná sestra")
        return "zdravotna_sestra", notes
    if position == "logoped":
        return "logoped", notes
    if position == "fyzioterapeut":
        return "fyzioterapeut", notes
    if position == "odborny riaditel" or "odborny riaditel" in contract:
        return "odborny_riaditel", notes
    if position == "odborny garant":
        return "odborny_garant", notes
    if position.startswith("odborny garant pre ambulanciu psychiatra"):
        notes.append("pozícia zjednotená na odborný garant")
        return "odborny_garant", notes
    if position.startswith("odborny garant pre klinicku psychologiu"):
        notes.append("pozícia zjednotená na odborný garant")
        return "odborny_garant", notes
    if position == "odborny garant spodask" or "odborny garant spodask" in contract:
        notes.append("pozícia zjednotená na odborný garant")
        return "odborny_garant", notes
    if position == "programovy riaditel" or "programovy riaditel" in contract:
        return "programovy_riaditel", notes
    if position == "generalna riaditelka" or "generalna riaditelka" in contract:
        return "generalna_riaditelka", notes
    if position == "financna riaditelka" or contract == "financny riaditel":
        return "financna_riaditelka", notes
    if position == "financny manazer" or contract == "financny manazer":
        return "financny_manazer", notes
    if position == "projektovy manazer" or contract == "projektovy manazer":
        return "projektovy_manazer", notes
    if position == "apz":
        notes.append("pozícia odvodená z APZ placeholdera na projektový manažér")
        return "projektovy_manazer", notes
    if position == "prevadzkova manazerka / odborna garantka podprogramu pre osoby so zdravotnym znevyhodnenim":
        notes.append("pozícia skrátená na prevádzková manažérka")
        return "prevadzkova_manazerka", notes
    if position == "personalista":
        return "personalista", notes
    if position == "mzdova uctovnicka":
        return "mzdova_uctovnicka", notes
    if position == "uctovnicka":
        return "uctovnicka", notes
    if position == "recepcna":
        return "recepcna", notes
    if position in {"recepcny centra", "recepcna centra"}:
        notes.append("pozícia normalizovaná na recepčná")
        return "recepcna", notes
    if position == "upratovacka":
        return "upratovacka", notes
    if position == "vyskumny/vyvojovy pracovnik":
        return "vyskumno_vyvojovy_pracovnik", notes
    if contract.startswith("odborny/a pracovnik/cka pre socialnu inkluziu"):
        notes.append("pozícia odvodená zo zmluvnej pozície")
        return "socialna_inkluzia_pracovnik", notes

    raise ValueError(f"Unmapped position: position={raw_position!r}, contract={raw_contract_position!r}, program={program_code!r}")


def canonical_manager_aliases(name: str) -> set[str]:
    normalized = normalize_text(name)
    folded = fold_text(normalized)
    aliases = {folded}
    parts = normalized.split()
    if len(parts) == 2:
        aliases.add(f"{fold_text(parts[1])} {fold_text(parts[0])}")
    return aliases


def build_manager_lookup(employee_names: list[str]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for name in employee_names:
        employee_id = employee_xmlid(name)
        for alias in canonical_manager_aliases(name):
            lookup[alias] = employee_id
    return lookup


def write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def collect_rows(source_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_idx, row in enumerate(reader, start=2):
            record = {header: normalize_text(row.get(header, "")) for header in SOURCE_HEADERS}
            if not any(record.values()):
                continue
            if not record["Priezvisko a meno"]:
                continue
            record["__row__"] = row_idx
            rows.append(record)
    return rows


def parse_location_tokens(raw_location: str) -> tuple[str, list[str], list[str], list[str]]:
    location = normalize_location(raw_location)
    tokens = split_locations(location)
    importable_sites: list[str] = []
    unresolved: list[str] = []
    notes: list[str] = []
    for token in tokens:
        folded = fold_text(token).upper()
        if folded in REGION_TOKEN_MAP:
            unresolved.append(token)
            continue
        importable_sites.append(token)

    if len(importable_sites) > 1:
        notes.append(f"viac lokalít mapovaných do pracovísk: {', '.join(importable_sites)}")
    if unresolved:
        notes.append(f"nemapovateľné lokalizačné časti: {', '.join(unresolved)}")

    main_site = importable_sites[0] if importable_sites else ""
    secondary_sites = importable_sites[1:] if len(importable_sites) > 1 else []
    return location, [main_site] if main_site else [], secondary_sites, notes


def load_wage_seed_job_names() -> dict[str, set[str]]:
    seed_path = Path(__file__).resolve().parents[1] / "data" / "wage" / "job_regime_mapping_seeds.csv"
    mappings: dict[str, set[str]] = {}
    with seed_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            mappings.setdefault(row["regime"], set()).add(fold_text(row["job_name"]))
    return mappings


def build_wage_mapping_issue(program_code: str, program_classification: str, job_name: str, wage_seed_job_names: dict[str, set[str]]) -> list[str]:
    if program_classification != "mapped":
        return []
    regime = PROGRAM_REGIME_BY_CODE.get(program_code)
    if not regime:
        return [f"program {program_code} nemá definovaný zákonný mzdový režim"]
    if fold_text(job_name) not in wage_seed_job_names.get(regime, set()):
        return [f"chýba seed mapovanie pozície `{job_name}` pre režim `{regime}`"]
    return []


def clean_rows(source_rows: list[dict[str, str]]) -> list[CleanedRow]:
    employee_names = [normalize_text(row["Priezvisko a meno"]) for row in source_rows if normalize_text(row["Priezvisko a meno"])]
    manager_lookup = build_manager_lookup(employee_names)
    wage_seed_job_names = load_wage_seed_job_names()
    cleaned: list[CleanedRow] = []

    for row in source_rows:
        source_row = row["__row__"]
        title = normalize_text(row["Titul"])
        name = normalize_text(row["Priezvisko a meno"])
        raw_employer = normalize_text(row["Zamestnávateľ"])
        raw_program = normalize_text(row["Program,do ktorého patria"])
        raw_contract_position = normalize_text(row["Pozícia podľa pracovnej zmluvy"])
        raw_position = normalize_text(row["Pozícia"])
        raw_manager = normalize_text(row["Priamy nadriadený"])
        raw_location = normalize_text(row["Lokácia"])
        raw_email = normalize_text(row["Email"])
        raw_phone = normalize_text(row["TEL"])

        org_unit_code, org_unit_name, org_unit_mapping_status = map_organizational_unit(raw_employer)
        program_code, program_name, program_classification = classify_program(raw_program)

        review_notes: list[str] = []
        missing_field_notes: list[str] = []
        manager_notes: list[str] = []
        location_notes: list[str] = []
        wage_mapping_notes: list[str] = []
        program_notes: list[str] = []

        if org_unit_mapping_status.startswith("default"):
            review_notes.append(f"organizačná zložka defaultovaná z `{raw_employer or 'prázdneho zamestnávateľa'}`")

        if program_classification in {"note", "normalized_from_note", "unmapped"}:
            program_notes.append(f"program potrebuje ručné posúdenie: `{raw_program or 'prázdny'}`")
            review_notes.extend(program_notes)

        job_key, job_notes = resolve_job(raw_position, raw_contract_position, program_code)
        review_notes.extend(job_notes)
        job_name, department_key = JOB_SPECS[job_key]
        job_name = sentence_case(job_name)
        department_name = sentence_case(DEPARTMENTS[department_key])

        location, main_site_parts, secondary_site_names, parsed_location_notes = parse_location_tokens(raw_location)
        location_notes.extend(parsed_location_notes)
        review_notes.extend(parsed_location_notes)
        main_site_name = main_site_parts[0] if main_site_parts else ""

        email, email_notes = clean_email(raw_email)
        missing_field_notes.extend(email_notes)
        review_notes.extend(email_notes)

        mobile_phone, work_phone, phone_notes = clean_phone(raw_phone)
        missing_field_notes.extend(phone_notes)
        review_notes.extend(phone_notes)

        manager_name = ""
        manager_employee_id = ""
        if raw_manager and fold_text(raw_manager) not in {"n/a", "na"}:
            manager_id = manager_lookup.get(fold_text(raw_manager))
            if not manager_id:
                parts = normalize_text(raw_manager).split()
                if len(parts) == 2:
                    manager_id = manager_lookup.get(f"{fold_text(parts[1])} {fold_text(parts[0])}")
            if manager_id:
                manager_employee_id = manager_id
                manager_name = next(candidate for candidate in employee_names if employee_xmlid(candidate) == manager_id)
            else:
                manager_notes.append(f"nadriadený `{raw_manager}` sa nepodarilo spárovať")
                review_notes.extend(manager_notes)
        elif raw_manager:
            manager_notes.append("nadriadený bol označený N/A a neimportuje sa")
            review_notes.extend(manager_notes)

        wage_program_code = program_code if program_classification == "mapped" else ""
        wage_mapping_notes.extend(build_wage_mapping_issue(program_code, program_classification, job_name, wage_seed_job_names))
        review_notes.extend(wage_mapping_notes)

        import_action = "import"
        skip_reason = ""
        if program_code == "NO_IMPORT":
            import_action = "skip"
            skip_reason = "riadok označený `nedávať`"

        status = "ready" if not review_notes else "review"

        cleaned.append(
            CleanedRow(
                source_row=source_row,
                title=title,
                name=name,
                raw_employer=raw_employer,
                org_unit_code=org_unit_code,
                org_unit_name=org_unit_name,
                org_unit_mapping_status=org_unit_mapping_status,
                raw_program=raw_program,
                raw_contract_position=raw_contract_position,
                raw_position=raw_position,
                raw_manager=raw_manager,
                raw_location=raw_location,
                raw_email=raw_email,
                raw_phone=raw_phone,
                program_code=program_code,
                program_name=program_name,
                program_classification=program_classification,
                wage_program_code=wage_program_code,
                job_key=job_key,
                job_name=job_name,
                department_key=department_key,
                department_name=department_name,
                manager_name=manager_name,
                manager_employee_id=manager_employee_id,
                work_location=location,
                main_site_name=main_site_name,
                secondary_site_names=secondary_site_names,
                location_unresolved=[note.split(": ", 1)[1] for note in location_notes if ": " in note and note.startswith("nemapovateľné")],
                work_email=email,
                mobile_phone=mobile_phone,
                work_phone=work_phone,
                import_action=import_action,
                skip_reason=skip_reason,
                status=status,
                review_note="; ".join(review_notes),
                employee_id=employee_xmlid(name),
                missing_field_notes=missing_field_notes,
                manager_notes=manager_notes,
                location_notes=location_notes,
                wage_mapping_notes=wage_mapping_notes,
                program_notes=program_notes,
            )
        )

    return cleaned


def export_outputs(cleaned_rows: list[CleanedRow], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    employee_rows = [
        {
            "id": row.employee_id,
            "title_academic": row.title,
            "name": row.name,
            "job_id/id": job_xmlid(row.job_key),
            "department_id/id": department_xmlid(row.department_key),
            "parent_id/id": row.manager_employee_id,
            "address_id/id": location_xmlid(row.main_site_name) if row.main_site_name else "",
            "work_location": row.work_location,
            "main_site_name": row.main_site_name,
            "secondary_site_names": "|".join(row.secondary_site_names),
            "organizational_unit_id/id": organizational_unit_xmlid(row.org_unit_code),
            "contract_position": row.raw_contract_position,
            "work_email": row.work_email,
            "private_phone": "",
            "work_phone": row.mobile_phone or row.work_phone,
            "x_source_row": str(row.source_row),
            "x_raw_employer": row.raw_employer,
            "x_org_unit_code": row.org_unit_code,
            "x_org_unit_mapping_status": row.org_unit_mapping_status,
            "x_raw_program": row.raw_program,
            "x_program_normalized": row.program_code or row.program_name,
            "x_wage_program_code": row.wage_program_code,
            "x_raw_contract_position": row.raw_contract_position,
            "x_raw_position": row.raw_position,
            "x_raw_manager": row.raw_manager,
            "x_location_unresolved": " | ".join(row.location_unresolved),
            "x_import_action": row.import_action,
            "x_skip_reason": row.skip_reason,
            "x_normalization_status": row.status,
            "x_review_note": row.review_note,
        }
        for row in cleaned_rows
    ]

    job_rows = [
        {
            "id": job_xmlid(job_key),
            "name": job_name,
            "x_department_code": department_xmlid(department_key),
        }
        for job_key, (job_name, department_key) in sorted(JOB_SPECS.items(), key=lambda item: item[1][0])
        if any(row.job_key == job_key and row.import_action == "import" for row in cleaned_rows)
    ]

    department_rows = [
        {"id": department_xmlid(department_key), "name": department_name}
        for department_key, department_name in sorted(DEPARTMENTS.items(), key=lambda item: item[1])
        if any(row.department_key == department_key and row.import_action == "import" for row in cleaned_rows)
    ]

    location_values = sorted({
        site_name
        for row in cleaned_rows
        for site_name in [row.main_site_name, *row.secondary_site_names]
        if site_name
    })
    location_rows = [
        {
            "id": location_xmlid(city),
            "name": f"Work location - {city}",
            "type": "other",
            "city": city,
            "country_id/id": "base.sk",
        }
        for city in location_values
    ]

    program_rows = []
    seen_programs = set()
    for row in sorted(cleaned_rows, key=lambda item: (item.raw_program, item.source_row)):
        if row.raw_program in seen_programs:
            continue
        seen_programs.add(row.raw_program)
        program_rows.append(
            {
                "raw_program": row.raw_program,
                "normalized_program_code": row.program_code,
                "normalized_program_name": row.program_name,
                "classification": row.program_classification,
            }
        )

    employee_path = output_dir / "hr_employee_import.csv"
    job_path = output_dir / "hr_job_import.csv"
    department_path = output_dir / "hr_department_import.csv"
    location_path = output_dir / "res_partner_location_import.csv"
    program_path = output_dir / "program_normalization.csv"
    review_path = output_dir / "employee_cleanup_review.md"
    missing_path = output_dir / "employee_import_missing_fields_sk.md"

    write_csv(employee_path, EMPLOYEE_HEADERS, employee_rows)
    write_csv(job_path, JOB_HEADERS, job_rows)
    write_csv(department_path, DEPARTMENT_HEADERS, department_rows)
    write_csv(location_path, LOCATION_HEADERS, location_rows)
    write_csv(program_path, PROGRAM_HEADERS, program_rows)
    review_text = build_review_report(cleaned_rows)
    missing_text = build_missing_fields_report(cleaned_rows)
    review_path.write_text(review_text, encoding="utf-8")
    missing_path.write_text(missing_text, encoding="utf-8")

    return {
        "employee": employee_path,
        "job": job_path,
        "department": department_path,
        "location": location_path,
        "program": program_path,
        "review": review_path,
        "missing": missing_path,
    }


def build_review_report(cleaned_rows: list[CleanedRow]) -> str:
    review_rows = [row for row in cleaned_rows if row.review_note]
    unresolved_managers = [row for row in cleaned_rows if row.manager_notes]
    invalid_contacts = [row for row in cleaned_rows if row.missing_field_notes]
    noisy_programs = [row for row in cleaned_rows if row.program_notes]
    position_judgments = [row for row in cleaned_rows if "pozícia" in row.review_note]
    multi_locations = [row for row in cleaned_rows if row.location_notes]

    sections = [
        "# Employee Cleanup Review",
        "",
        f"- Source rows processed: {len(cleaned_rows)}",
        f"- Rows requiring review: {len(review_rows)}",
        f"- Unresolved or omitted managers: {len(unresolved_managers)}",
        f"- Contact cleanup issues: {len(invalid_contacts)}",
        f"- Program notes/noise rows: {len(noisy_programs)}",
        f"- Non-trivial position normalizations: {len(position_judgments)}",
        f"- Rows with multiple or partial locations: {len(multi_locations)}",
        "",
        "## Rows Requiring Review",
        "",
    ]

    for row in review_rows:
        sections.append(
            f"- Row {row.source_row}: {row.name} | job `{row.job_name}` | dept `{row.department_name}` | {row.review_note}"
        )

    return "\n".join(sections) + "\n"


def _section_lines(title: str, rows: list[str]) -> list[str]:
    return [f"## {title}", ""] + (rows or ["- nič"]) + [""]


def build_missing_fields_report(cleaned_rows: list[CleanedRow]) -> str:
    skipped = [
        f"- Riadok {row.source_row}: {row.name} | dôvod: {row.skip_reason}"
        for row in cleaned_rows
        if row.import_action == "skip"
    ]
    missing_fields = [
        f"- Riadok {row.source_row}: {row.name} | {', '.join(row.missing_field_notes)}"
        for row in cleaned_rows
        if row.missing_field_notes
    ]
    location_issues = [
        f"- Riadok {row.source_row}: {row.name} | {'; '.join(row.location_notes)}"
        for row in cleaned_rows
        if row.location_notes
    ]
    manager_issues = [
        f"- Riadok {row.source_row}: {row.name} | {'; '.join(row.manager_notes)}"
        for row in cleaned_rows
        if row.manager_notes
    ]
    wage_issues = [
        f"- Riadok {row.source_row}: {row.name} | {'; '.join(row.wage_mapping_notes)}"
        for row in cleaned_rows
        if row.wage_mapping_notes
    ]
    program_issues = [
        f"- Riadok {row.source_row}: {row.name} | {'; '.join(row.program_notes)}"
        for row in cleaned_rows
        if row.program_notes and row.import_action == "import"
    ]

    lines = [
        "# Chýbajúce alebo neimportované údaje zamestnancov",
        "",
        f"- Spracované riadky: {len(cleaned_rows)}",
        f"- Importované riadky: {sum(1 for row in cleaned_rows if row.import_action == 'import')}",
        f"- Preskočené riadky: {sum(1 for row in cleaned_rows if row.import_action == 'skip')}",
        "",
    ]
    lines.extend(_section_lines("Neimportované riadky", skipped))
    lines.extend(_section_lines("Neimportované polia", missing_fields))
    lines.extend(_section_lines("Nejednoznačné lokácie", location_issues))
    lines.extend(_section_lines("Chýbajúci manažéri", manager_issues))
    lines.extend(_section_lines("Chýbajúce wage mapovanie pozície", wage_issues))
    lines.extend(_section_lines("Chýbajúci alebo manuálne nedoriešený program", program_issues))
    return "\n".join(lines).rstrip() + "\n"


def validate_outputs(cleaned_rows: list[CleanedRow]) -> None:
    assert cleaned_rows, "No employee rows processed"
    assert all(row.name == row.name.strip() for row in cleaned_rows)
    assert all(row.job_key in JOB_SPECS for row in cleaned_rows)
    assert all(row.department_key in DEPARTMENTS for row in cleaned_rows)
    assert all(row.org_unit_code for row in cleaned_rows)
    assert any(row.import_action == "skip" for row in cleaned_rows), "Expected at least one skipped row"
    assert any(row.wage_program_code for row in cleaned_rows), "Expected at least one deterministic wage program"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    source_rows = collect_rows(args.source_csv)
    cleaned_rows = clean_rows(source_rows)
    validate_outputs(cleaned_rows)
    outputs = export_outputs(cleaned_rows, args.output_dir)

    print(f"Processed {len(cleaned_rows)} employee rows.")
    for label, path in outputs.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
