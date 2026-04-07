import logging

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _backfill_reporting_program(env)
    _migrate_legacy_trzby_overrides(env)


def _backfill_reporting_program(env):
    projects = env["tenenet.project"].with_context(active_test=False).search([
        ("reporting_program_id", "=", False),
        ("program_ids", "!=", False),
    ])
    updated = 0
    for project in projects:
        if len(project.program_ids) == 1:
            project.reporting_program_id = project.program_ids[:1]
            updated += 1
    _logger.info("Backfilled reporting_program_id on %d project(s).", updated)


def _migrate_legacy_trzby_overrides(env):
    override_model = env["tenenet.pl.program.override"].with_context(include_separators=True)
    sales_model = env["tenenet.program.sales.entry"]
    rows = override_model.search([
        ("row_key", "=", "trzby"),
        ("amount", "!=", 0.0),
    ])
    created = 0
    for row in rows:
        existing = sales_model.search([
            ("program_id", "=", row.program_id.id),
            ("period", "=", row.period),
            ("sale_type", "=", "legacy_unclassified"),
            ("source_ref", "=", "legacy:tenenet.pl.program.override.trzby"),
        ], limit=1)
        if existing:
            continue
        sales_model.create({
            "program_id": row.program_id.id,
            "period": fields.Date.to_date(row.period),
            "sale_type": "legacy_unclassified",
            "amount": row.amount,
            "source_ref": "legacy:tenenet.pl.program.override.trzby",
            "note": row.note or "Migrované z pôvodného P&L override riadku 'trzby'.",
        })
        created += 1
    _logger.info("Migrated %d legacy trzby override row(s) to tenenet.program.sales.entry.", created)
