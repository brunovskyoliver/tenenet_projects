# AGENTS.md — AI Agent Instructions for Tenenet Projects

This file provides instructions for AI coding agents (Windsurf/Cascade, Cursor, Claude Code, etc.) working on the Tenenet Odoo v19 module suite.

---

## Project Overview

**Company**: Tenenet — Slovak NGO providing social services (child protection, crisis intervention, early intervention, community centers).

**Goal**: Replace Excel-based project management with Odoo v19 modules covering:
- Project tracking with budgets, donors, and programs
- Employee allocation across projects (monthly hours & costs)
- Utilization monitoring (capacity vs. actual hours)
- P&L reporting by program with allocation keys

**Module technical name**: `tenenet_projects`
**Odoo version**: 19.0

---

## Directory Structure

```
/Users/oliver/odoo-dev/addons/
├── tenenet_projects/              # Main Odoo module
│   ├── __init__.py
│   ├── __manifest__.py
│   ├── AGENTS.md                  # THIS FILE
│   ├── plans/                     # Implementation plans per module
│   ├── models/                    # Python model files
│   ├── views/                     # XML view definitions
│   ├── security/                  # ACL + record rules
│   ├── wizard/                    # Import wizards
│   ├── data/                      # Seed data (programs, donors)
│   ├── report/                    # QWeb reports
│   ├── tests/                     # Unit tests
│   ├── controllers/               # HTTP endpoints
│   └── static/                    # Assets (JS, CSS, icons)
├── docs/                          # Documentation for AI agents
│   ├── migration-data/            # Source Excel files
│   ├── data-model.md              # Odoo model definitions
│   ├── data-relations.md          # ER diagram, relationships
│   ├── excel-column-mapping.md    # Excel col → Odoo field mapping
│   ├── implementation-guide.md    # Full implementation process
│   └── glossary-sk.md             # Slovak → English terms
└── .windsurf/skills/odoo-19/      # Odoo v19 API reference
    └── references/                # 18 guide files
```

---

## Before You Code: Read These First

Depending on your task, read the relevant files:

| Task | Read First |
|------|-----------|
| Creating a new model | `docs/data-model.md` + `references/odoo-19-model-guide.md` + `references/odoo-19-field-guide.md` |
| Creating views | `docs/data-model.md` + `references/odoo-19-view-guide.md` |
| Adding computed fields | `references/odoo-19-decorator-guide.md` |
| Setting up security | `references/odoo-19-security-guide.md` |
| Building import wizards | `docs/excel-column-mapping.md` + `references/odoo-19-development-guide.md` |
| Writing tests | `references/odoo-19-testing-guide.md` |
| Understanding data | `docs/data-relations.md` + `docs/glossary-sk.md` |
| Creating reports | `references/odoo-19-reports-guide.md` |
| Adding actions/menus | `references/odoo-19-actions-guide.md` |
| Performance issues | `references/odoo-19-performance-guide.md` |
| Migration scripts | `references/odoo-19-migration-guide.md` |

---

## Coding Conventions

### Odoo v19 Mandatory Patterns

These are **breaking changes** in Odoo 19. Using the old pattern will cause errors:

```python
# SQL Constraints — use models.Constraint, NOT _sql_constraints
_unique_code = models.Constraint('UNIQUE(code)', 'Code must be unique!')

# Delete validation — use @api.ondelete, NOT override unlink()
@api.ondelete(at_uninstall=False)
def _unlink_check(self):
    if self.state == 'done':
        raise UserError("Cannot delete completed records")
```

```xml
<!-- List views — use <list>, NOT <tree> -->
<list string="Projects">
    <field name="name"/>
</list>

<!-- Dynamic visibility — use invisible=, NOT attrs= -->
<field name="budget" invisible="state != 'confirmed'"/>
```

### Naming Conventions

| Item | Convention | Example |
|------|-----------|---------|
| Model class | CamelCase | `TenenetProject` |
| Model `_name` | dot-separated lowercase | `tenenet.project` |
| Field names | snake_case | `program_director_id` |
| View XML IDs | `module.model_viewtype` | `tenenet_projects.tenenet_project_form` |
| Menu XML IDs | `module.menu_name` | `tenenet_projects.menu_tenenet_root` |
| File names | snake_case matching model | `tenenet_project.py`, `tenenet_project_views.xml` |

### Model Creation Order

Always respect FK dependencies:
1. `tenenet.program` (independent)
2. `tenenet.donor` (independent)
3. `hr.employee` extension (depends on `hr`)
4. `tenenet.project` (FK → program, donor, employee)
5. `tenenet.employee.allocation` (FK → employee, project)
6. `tenenet.utilization` (FK → employee)
7. `tenenet.pl.line` (FK → employee, program)

### Import Order in `__init__.py`

```python
from . import tenenet_program
from . import tenenet_donor
from . import hr_employee
from . import tenenet_project
from . import tenenet_employee_allocation
from . import tenenet_utilization
from . import tenenet_pl_line
```

---

## Data Handling Rules

### Slovak Language Data

- All data in Excel files uses Slovak language
- Employee names, project names, comments are in Slovak
- Use `docs/glossary-sk.md` for translations
- Ensure UTF-8 encoding for Slovak characters: ä, č, ď, é, í, ľ, ĺ, ň, ó, ô, ŕ, š, ť, ú, ý, ž
- Field labels in Odoo should be in English; user-facing strings can be in Slovak via translations

### Currency

- All monetary values are in **EUR**
- Always include `currency_id` field alongside Monetary fields
- Default: `self.env.ref('base.EUR')`

### Date Formats

- Excel dates may be `datetime` objects or strings like "12.2.2025"
- Some contain typos (e.g., "12.2.02.024")
- Parse with: `datetime.strptime(date_str, '%d.%m.%Y')` with error handling

### Employee Name Matching

- Names differ across files (formal vs. informal, with/without titles)
- Some employees have split contracts ("Name" + "Name 2h")
- Use normalized comparison: strip, lowercase, split on spaces
- Log unmatched names instead of raising errors

---

## Testing Requirements

Before marking any feature as complete:

1. **Unit tests** for all computed fields
2. **Constraint tests** (verify unique constraints raise on duplicates)
3. **Import wizard tests** with sample data
4. **ACL tests** (user vs. manager permissions)

Run tests with:
```bash
./odoo-bin -d testdb -i tenenet_projects --test-enable --stop-after-init
```

---

## Migration Data Location

Source Excel files are at `docs/migration-data/`:

| File | Content | Primary Target Models |
|------|---------|----------------------|
| `00_Project Summary_2026.xlsx` | Projects, donors, budgets | `tenenet.project`, `tenenet.donor` |
| `9.1.26 Rozuctovanie zamestnancov...xlsx` | Employees, allocations, costs | `hr.employee`, `tenenet.employee.allocation` |
| `2026_vytazenost 04 02 2026.xlsx` | Employee utilization | `tenenet.utilization` |
| `P&L po programoch 2025...xlsx` | P&L by program, allocation keys | `tenenet.pl.line`, `tenenet.program` |

See `docs/excel-column-mapping.md` for exact column-to-field mappings.

---

## Key Odoo v19 References

All at `.windsurf/skills/odoo-19/references/`:

| File | When to Use |
|------|-------------|
| `odoo-19-model-guide.md` | ORM, CRUD, domains, recordsets |
| `odoo-19-field-guide.md` | Field types, parameters, computed fields |
| `odoo-19-view-guide.md` | XML views, actions, menus |
| `odoo-19-decorator-guide.md` | @api.depends, @api.constrains, @api.ondelete |
| `odoo-19-security-guide.md` | ACL, record rules, groups |
| `odoo-19-development-guide.md` | Module structure, wizards, manifest |
| `odoo-19-testing-guide.md` | Test classes, assertions |
| `odoo-19-performance-guide.md` | N+1 prevention, batch operations |
| `odoo-19-reports-guide.md` | QWeb reports, PDF/HTML |
| `odoo-19-actions-guide.md` | Window actions, server actions, cron |
| `odoo-19-mixins-guide.md` | mail.thread, activities |
| `odoo-19-migration-guide.md` | Migration scripts, hooks |
