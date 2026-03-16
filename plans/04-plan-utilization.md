# Plan 04: Utilization Tracking Model

Monthly utilization summary per employee with KPI computations.

---

## Scope

- `tenenet.utilization` — Tracks capacity vs. actual hours, computes utilization rate

## Prerequisites

- `hr.employee` extension (Plan 01)

## Tasks

### 1. Create `tenenet.utilization` model
- **File**: `models/tenenet_utilization.py`
- **Fields**: See `docs/data-model.md` → tenenet.utilization
- **Computed fields** (all stored):
  - `hours_project_total` = sum(PP, NP, travel, training, ambulance, international)
  - `hours_non_project_total` = sum(vacation, doctor, sick, ballast)
  - `utilization_rate` = hours_project_total / capacity_hours
  - `utilization_status` = 'ok' if rate >= 0.8 else 'warning'
  - `non_project_rate` = hours_non_project_total / capacity_hours
  - `non_project_status` = 'ok' if rate <= 0.25 else 'warning'
  - `hours_diff` = hours_project_total + hours_non_project_total - capacity_hours
- **Constraint**: UNIQUE(employee_id, period)

### 2. Views
- **File**: `views/tenenet_utilization_views.xml`
- **List**: employee, period, capacity, project hours, utilization rate (progress bar), status
- **Form**: Full hour breakdown with visual indicators
- **Search**: Filter by status (OK/warning), group by employee/period
- **Pivot**: For dashboard — rows=employee, columns=period, values=utilization_rate
- **Graph**: Bar chart of utilization by employee

### 3. KPI Thresholds
Match the Excel logic:
- Utilization ≥ 80% → OK (green)
- Utilization < 80% → Warning (red "!")
- Non-project ≤ 25% → OK
- Non-project > 25% → Warning

### 4. Tests
- Verify all 6 computed fields
- Test division by zero (capacity = 0)
- Test status thresholds at boundary values
- Unique constraint test

## Data Source
- `2026_vytazenost 04 02 2026.xlsx` — main sheet + Hárok1

## References
- `docs/data-model.md` → tenenet.utilization
- `docs/data-relations.md` → Computed Field Dependencies
- `docs/excel-column-mapping.md` → File 3 mapping
