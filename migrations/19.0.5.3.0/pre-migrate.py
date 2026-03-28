"""
Migration 19.0.5.2.0 → 19.0.5.3.0

1. Migrate receipt records: existing records have year+amount but no date_received.
   Set date_received = first day of that year so they don't violate the new NOT NULL constraint.
2. Drop old columns from tenenet_project that were removed (handled by Odoo ORM automatically,
   but we ensure receipt migration happens first).
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _migrate_receipt_dates(cr)


def _migrate_receipt_dates(cr):
    """Add date_received column and populate from existing year field."""
    # Add the column if it doesn't exist yet (pre-migration: schema not yet updated)
    cr.execute("""
        ALTER TABLE tenenet_project_receipt
        ADD COLUMN IF NOT EXISTS date_received DATE
    """)

    # Populate from year (first day of that year as a safe default)
    cr.execute("""
        UPDATE tenenet_project_receipt
        SET date_received = make_date(year, 1, 1)
        WHERE date_received IS NULL AND year IS NOT NULL AND year > 0
    """)

    # Fallback for records without year
    cr.execute("""
        UPDATE tenenet_project_receipt
        SET date_received = CURRENT_DATE
        WHERE date_received IS NULL
    """)

    cr.execute("SELECT COUNT(*) FROM tenenet_project_receipt WHERE date_received IS NOT NULL")
    count = cr.fetchone()[0]
    _logger.info("Migrated date_received on %d receipt record(s).", count)
