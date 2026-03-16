# Plan 02: Project Model

Core project entity with FK dependencies on program, donor, and employee.

---

## Scope

- `tenenet.project` — Funded projects with budgets, timelines, managers, and financial tracking

## Prerequisites

- `tenenet.program` (Plan 01)
- `tenenet.donor` (Plan 01)
- `hr.employee` extension (Plan 01)

## Tasks

### 1. Create `tenenet.project` model
- **File**: `models/tenenet_project.py`
- **Fields**: See `docs/data-model.md` → tenenet.project section
- **Key relations**:
  - `program_id` → tenenet.program (Many2one, ondelete=restrict)
  - `donor_id` → tenenet.donor (Many2one, ondelete=restrict)
  - `program_director_id`, `project_manager_id`, `financial_manager_id` → hr.employee
  - `allocation_ids` → tenenet.employee.allocation (One2many)
- **Computed fields**:
  - `received_total` = sum(received_2020..2026)
  - `budget_diff` = amount_contracted - received_total
- **Currency**: EUR default via `currency_id`

### 2. Views
- **File**: `views/tenenet_project_views.xml`
- **List**: year, code, name, program, donor, budget, dates, semaphore (badge widget)
- **Form**: Two column groups (identity + dates/budget), notebook pages (Managers, Finance, Allocations, Settlement, Notes)
- **Search**: Filter by active, group by program/year/donor

### 3. Actions & Menus
- Window action for project list/form
- Menu: Tenenet → Projects → All Projects

### 4. Tests
- Create project with all FK relations
- Verify received_total computation
- Verify budget_diff computation
- Test semaphore selection values

## References
- `docs/data-model.md` → tenenet.project
- `docs/excel-column-mapping.md` → "Projects Summary MG" mapping
- `references/odoo-19-decorator-guide.md` — @api.depends
