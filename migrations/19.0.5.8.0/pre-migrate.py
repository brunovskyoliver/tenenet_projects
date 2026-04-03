"""
Migration 19.0.5.7.2 → 19.0.5.8.0

Remove the deprecated project comments column before registry upgrade.
"""


def migrate(cr, version):
    cr.execute("ALTER TABLE tenenet_project DROP COLUMN IF EXISTS comments")

