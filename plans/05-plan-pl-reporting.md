# Plan 05: P&L Reporting by Program

Monthly profit & loss lines per employee per program, with allocation key logic.

---

## Scope

- `tenenet.pl.line` — Monthly cost entry linking employee to program
- Allocation key computation on `tenenet.program`

## Prerequisites

- `tenenet.program` (Plan 01)
- `hr.employee` extension (Plan 01)

## Tasks

### 1. Create `tenenet.pl.line` model
- **File**: `models/tenenet_pl_line.py`
- **Fields**:
  - `employee_id` → hr.employee
  - `program_id` → tenenet.program
  - `period` — Date (1st of month)
  - `amount` — Monetary (monthly cost)
  - `annual_total` — computed sum of same employee+program for the year
- **Constraint**: UNIQUE(employee_id, program_id, period)

### 2. Program allocation_pct computation
- Add/refine `_compute_allocation_pct` on `tenenet.program`
- Formula: `self.headcount / sum(all programs' headcount)`
- Uses `_read_group` for efficient aggregation

### 3. Views
- **File**: `views/tenenet_pl_line_views.xml`
- **List**: employee, program, period, amount
- **Pivot** (primary view): Rows=Program→Employee, Columns=Period(month), Values=amount(sum)
- **Graph**: Stacked bar — programs on x-axis, monthly amounts stacked
- **Search**: Group by program, period, employee

### 4. Menu
- Tenenet → Reporting → P&L by Program

### 5. Tests
- Create P&L lines, verify annual_total aggregation
- Verify allocation_pct sums to ~1.0 across all programs
- Unique constraint test

## Data Source
- `P&L po programoch 2025 @ 25 Nov 25.xlsx` — main sheet (employee × month matrix)
- "Allocation key" sheet for program headcount/percentage

## References
- `docs/data-model.md` → tenenet.pl.line, tenenet.program
- `docs/excel-column-mapping.md` → File 4 mapping
- `references/odoo-19-performance-guide.md` — _read_group for aggregation
