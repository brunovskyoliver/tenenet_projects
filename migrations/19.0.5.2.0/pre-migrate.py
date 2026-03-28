"""
Migration 19.0.5.1.0 → 19.0.5.2.0

Converts program_id (Many2one) on tenenet.project to program_ids (Many2many).

Runs BEFORE Odoo updates the schema so we can still read the old program_id column
and pre-populate the new relation table.  Odoo will then create the table (if it
does not yet exist) and leave the pre-populated rows intact.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # Create the many2many relation table (Odoo will not re-create if it exists)
    cr.execute("""
        CREATE TABLE IF NOT EXISTS tenenet_project_program_rel (
            project_id  INTEGER NOT NULL,
            program_id  INTEGER NOT NULL,
            PRIMARY KEY (project_id, program_id)
        )
    """)

    # Migrate existing program_id values → relation rows
    cr.execute("""
        SELECT id, program_id
        FROM tenenet_project
        WHERE program_id IS NOT NULL
    """)
    rows = cr.fetchall()
    if rows:
        cr.executemany(
            """
            INSERT INTO tenenet_project_program_rel (project_id, program_id)
            VALUES (%s, %s)
            ON CONFLICT (project_id, program_id) DO NOTHING
            """,
            rows,
        )
        _logger.info(
            "Migrated %d project→program links to tenenet_project_program_rel.", len(rows)
        )
    else:
        _logger.info("No existing program_id values found — nothing to migrate.")
