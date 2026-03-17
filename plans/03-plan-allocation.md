# Plan 03: Employee-Project Allocation Model

> ⚠️ **SUPERSEDED by Plan 09** (`09-plan-project-timesheet.md`).
> `tenenet.employee.allocation` is now a read-only archive model.
> All new data entry uses `tenenet.project.timesheet` via the project Timesheety tab.

Monthly allocation of employee time and cost to projects.

---

## Scope

- `tenenet.employee.allocation` — Junction model linking employees to projects per month

## Prerequisites

- `hr.employee` extension (Plan 01)
- `tenenet.project` (Plan 02)

## Tasks

### 1. Create `tenenet.employee.allocation` model
- **File**: `models/tenenet_employee_allocation.py`
- **Fields**:
  - `employee_id` → hr.employee (Many2one, cascade)
  - `project_id` → tenenet.project (Many2one, cascade)
  - `period` — Date (1st of month)
  - Hours: hours_pp, hours_np, hours_travel, hours_training, hours_ambulance, hours_international
  - `hours_total` — computed sum of all hour fields
  - Cost: gross_salary, deductions, total_labor_cost (computed)
  - Leave: hours_vacation, hours_sick, hours_doctor, hours_holidays
- **Constraint**: UNIQUE(employee_id, project_id, period)

### 2. Views
- **File**: `views/tenenet_allocation_views.xml`
- **List**: employee, project, period, hours_total, total_labor_cost
- **Form**: Full detail with hour breakdown and cost section
- **Search**: Filter by employee, project; group by period/project/employee
- **Pivot**: Rows=Employee, Columns=Period, Values=hours_total (for dashboard)

### 3. Tests
- Create allocation, verify hours_total computation
- Verify total_labor_cost = gross_salary + deductions
- Test unique constraint raises on duplicate employee+project+period
- Verify cascade delete from project and employee

## Data Source
- `Rozuctovanie zamestnancov` → individual employee sheets (rows 12+, per-project hours by month)
- `summary_*` sheets for cross-validation

## References
- `docs/data-model.md` → tenenet.employee.allocation
- `docs/excel-column-mapping.md` → "Meno Priezvisko - template" section
