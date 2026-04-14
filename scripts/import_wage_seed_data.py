"""
Run inside `odoo-bin shell -d <db>`:

    exec(open("tenenet_projects/scripts/import_wage_seed_data.py").read())
"""

env["tenenet.wage.table"]._load_default_wage_seed_data()
print("Loaded TENENET wage seed data.")
