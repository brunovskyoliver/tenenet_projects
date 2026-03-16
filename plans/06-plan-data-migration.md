# Plan 06: Data Migration (Excel Import Wizards)

Import wizards for migrating all 4 Excel workbooks into Odoo.

---

## Scope

- TransientModel wizards for each Excel file
- File upload → parse → create records
- Validation & error reporting

## Prerequisites

- All models from Plans 01–05

## Tasks

### 1. Import Programs Wizard
- **Source**: `P&L po programoch 2025` → "Allocation key" sheet
- **Target**: `tenenet.program`
- **Logic**: Read rows 2–12 (A=program name, B=headcount, C=allocation%)
- **File**: `wizard/import_programs.py`

### 2. Import Donors Wizard
- **Source**: `00_Project Summary_2026.xlsx` → "Projects Summary MG" cols H+I
- **Target**: `tenenet.donor`
- **Logic**: Extract unique donors from col I, classify type from col H
- **File**: `wizard/import_donors.py`

### 3. Import Employees Wizard
- **Source**: `9.1.26 Rozuctovanie zamestnancov` → "Zoznam zamestnancov" sheet
- **Target**: `hr.employee`
- **Logic**: Rows 2+, map cols A–I per `docs/excel-column-mapping.md`
- **Challenge**: Resolve `parent_id` (supervisor) by name lookup
- **File**: `wizard/import_employees.py`

### 4. Import Projects Wizard
- **Source**: `00_Project Summary_2026.xlsx` → "Projects Summary MG"
- **Target**: `tenenet.project`
- **Logic**: Rows 3+, map cols A–AR per mapping doc
- **Challenge**: Parse date strings, lookup program/donor/employee by name
- **File**: `wizard/import_projects.py`

### 5. Import Allocations Wizard
- **Source**: `9.1.26 Rozuctovanie zamestnancov` → individual employee sheets (130+)
- **Target**: `tenenet.employee.allocation`
- **Logic**: For each non-template/non-list sheet:
  1. Get employee from cell A1
  2. Read salary data (rows 5–7)
  3. Read project allocations (rows 12+, col B = project code)
  4. Create allocation records per month (cols C–H, J–O)
- **Challenge**: 173 sheets, name matching, project code resolution
- **File**: `wizard/import_allocations.py`

### 6. Import Utilization Wizard
- **Source**: `2026_vytazenost 04 02 2026.xlsx` → main sheet + Hárok1
- **Target**: `tenenet.utilization`
- **Logic**: Rows 2+, map cols A–AB per mapping doc
- **Challenge**: Determine period from filename
- **File**: `wizard/import_utilization.py`

### 7. Import P&L Wizard
- **Source**: `P&L po programoch 2025` → main sheet
- **Target**: `tenenet.pl.line`
- **Logic**: Track current program section, create 12 records per employee row
- **Challenge**: Detecting program header rows vs employee data rows
- **File**: `wizard/import_pl.py`

### 8. Wizard Views
- **Files**: `wizard/import_*_views.xml` — Form with file upload + "Import" button
- Menu: Tenenet → Configuration → Import Data (submenu per wizard)

### 9. Import Order
Must import in this sequence:
1. Programs
2. Donors
3. Employees (needs programs for context, donors for lookup)
4. Projects (needs programs, donors, employees)
5. Allocations (needs employees, projects)
6. Utilization (needs employees)
7. P&L Lines (needs employees, programs)

### 10. Error Handling
- Use `try/except` per row, collect errors
- After import, show summary: X created, Y skipped, Z errors
- Log unmatched names to `ir.logging` or display in wizard result

## References
- `docs/excel-column-mapping.md` — Definitive column mappings
- `docs/glossary-sk.md` — Slovak term lookups
- `references/odoo-19-development-guide.md` — Wizard patterns
