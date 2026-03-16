# Plan 01: Employee, Program & Donor Models

Foundation models with no complex FK dependencies.

---

## Scope

- `tenenet.program` — Program/service area (11 programs from P&L allocation key)
- `tenenet.donor` — Funding organizations
- `hr.employee` extension — Tenenet-specific fields on Odoo's HR employee model

## Tasks

### 1. Create `tenenet.program` model
- **File**: `models/tenenet_program.py`
- **Fields**: name, code, description, active, headcount, allocation_pct (computed), project_ids (One2many)
- **Constraint**: UNIQUE(code)
- **Views**: list, form, search
- **Seed data**: 11 programs from P&L "Allocation key" sheet (VCI, SCPP, AKP-deti, SPODASK, AVL, AKP-dosp, Nas a Vaz, KC, Zdrav Znev, SS projekty, Ostatne)

### 2. Create `tenenet.donor` model
- **File**: `models/tenenet_donor.py`
- **Fields**: name, donor_type (selection), contact_info, active, project_ids (One2many)
- **Views**: list, form, search
- **Seed data**: Donors extracted from Project Summary col H+I (deduplicated)

### 3. Extend `hr.employee`
- **File**: `models/hr_employee.py`
- **New fields**: tenenet_number, title_academic, position, education_info, work_hours, work_ratio, hourly_rate, allocation_ids, utilization_ids
- **View**: Inherit existing employee form to add Tenenet tab
- **Dependency**: Module must `depends` on `hr`

### 4. Views
- **Files**: `views/tenenet_program_views.xml`, `views/tenenet_donor_views.xml`, `views/hr_employee_views.xml`
- List + Form + Search for program and donor
- Inherited form view for employee (new notebook page "Tenenet")

### 5. Seed Data
- **Files**: `data/tenenet_program_data.xml`, `data/tenenet_donor_data.xml`
- Pre-populate programs and common donors

### 6. Tests
- Create program, verify constraint on duplicate code
- Create donor with valid type
- Create employee with Tenenet fields
- Verify program allocation_pct computation

## References
- `docs/data-model.md` — Model definitions
- `docs/excel-column-mapping.md` — "Allocation key" sheet, "Zoznam zamestnancov" sheet
- `references/odoo-19-field-guide.md` — Field types
- `references/odoo-19-model-guide.md` — Constraints, inheritance
