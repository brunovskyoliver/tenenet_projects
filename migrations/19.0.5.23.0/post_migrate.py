from odoo import SUPERUSER_ID, api


CASHFLOW_LABEL_MAP = {
    "Trzby AVL, AKP - poistovne SC": "Tržby AVL, AKP - poisťovne SC",
    "Trzby ostatne": "Tržby ostatné",
    "Trzby nove - PSC": "Tržby nové - PSC",
    "Trzby nove - PAS": "Tržby nové - PAS",
    "Ostatne trzby - 2%, dary": "Ostatné tržby - 2 %, dary",
    "Mzdy, stravne, CP a odvody - Kalia": "Mzdy, stravné, CP a odvody - Kalia",
    "Mzdy, stravne, CP a odvody - SCPP": "Mzdy, stravné, CP a odvody - SCPP",
    "Mzdy, stravne, CP a odvody - Wellnea, IDA tim": "Mzdy, stravné, CP a odvody - Wellnea, IDA tím",
    "Projektovy naklad - Vratka PU a ine vratky, AI Tutor": "Projektový náklad - vratka PU a iné vratky, AI Tutor",
    "Projektove naklady - ICM": "Projektové náklady - ICM",
    "Projektove naklady - Housing Led (prenajom bytov)": "Projektové náklady - Housing Led (prenájom bytov)",
    "Projektovy naklad -Guide, Stem, MinM, EASY": "Projektový náklad - Guide, Stem, MinM, EASY",
    "Prevadzkove N - PSC": "Prevádzkové náklady - PSC",
    "Prevadzkove N - Stavebne, architekt": "Prevádzkové náklady - stavebné práce a architekt",
    "Prevadzkove N - prevod do pokladne": "Prevádzkové náklady - prevod do pokladne",
    "Prevadzkove N - Platby kartou, vyber kartou": "Prevádzkové náklady - platby kartou a výber kartou",
    "EIRR, ASSP, AFB, K Cavoj": "Prevádzkové náklady - ostatné všeobecné náklady",
    "Investicne N - PAS Presov": "Investičné náklady - PAS Prešov",
    "Investicne N - PAS ZILINA": "Investičné náklady - PAS Žilina",
    "Financny N - Uver SLSP, kontokorent urok, transakcna dan - W": "Finančné náklady - úver SLSP, kontokorent, úrok, transakčná daň - W",
    "Prevadzkova N - HR costs - vzdelavanie (superv. a SK)": "Prevádzkové náklady - HR, vzdelávanie a supervízia",
    "Prevadzkova N - Market, PR costs (TT)": "Prevádzkové náklady - marketing a PR",
    "Prevadzkove N - Auta (poistenie, opravy), poistenie budov": "Prevádzkové náklady - poistenie a opravy, poistenie budov",
    "Prevadzkove N - energie": "Prevádzkové náklady - energie",
    "Prevadzkove N - IT slu & tlaciarne (DV)": "Prevádzkové náklady - IT služby a tlačiarne (DV)",
    "Prevadzkove N - najom": "Prevádzkové náklady - nájom",
    "Prevadzkove N - One-off items, VO, dane": "Prevádzkové náklady - dane, poplatky a jednorazové položky",
    "Prevadzkove N - Other general costs (n/m)": "Prevádzkové náklady - ostatné všeobecné náklady",
    "Prevadzkove N - Pravne sluzby (CLS), audit (JP)": "Prevádzkové náklady - právne služby (CLS) a audit (JP)",
    "Prevadzkove N - Tel a internet": "Prevádzkové náklady - telekomunikácie a internet",
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["tenenet.expense.type.config"]._load_default_operating_seed_data()

    overrides = env["tenenet.cashflow.global.override"].with_context(active_test=False).search([])
    for old_label, new_label in CASHFLOW_LABEL_MAP.items():
        rows = overrides.filtered(lambda rec: rec.row_label == old_label)
        if rows:
            rows.write({"row_label": new_label})
        project_rows = overrides.filtered(lambda rec: rec.project_label == old_label)
        if project_rows:
            project_rows.write({"project_label": new_label})
