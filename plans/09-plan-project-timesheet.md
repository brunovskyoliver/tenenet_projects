# Plan 09: Project Timesheet Grid & Tenenet Residual

Monthly timesheet entry per employee-project assignment, replacing `tenenet.employee.allocation`. Includes automatic Tenenet residual cost generation and `hr_holidays` leave auto-sync.

---

## Scope

- `tenenet.project.timesheet` — monthly hours per assignment (replaces `tenenet.employee.allocation`)
- `tenenet.employee.tenenet.cost` — auto-generated residual (salary not covered by projects)
- `hr.leave` override — auto-populate timesheet leave hours from approved Odoo leaves
- Editable inline list view inside project form (Timesheety tab)

## Prerequisites

- Plan 08 (`tenenet.project.assignment`)
- `hr_holidays` module

## Models

### `tenenet.project.timesheet`
- `assignment_id` (required, cascade) → `tenenet.project.assignment`
- `employee_id`, `project_id` — related (stored) from assignment
- `period` — Date (first of month)
- Hour fields: `hours_pp`, `hours_np`, `hours_travel`, `hours_training`, `hours_ambulance`, `hours_international`
- Leave fields: `hours_vacation`, `hours_sick`, `hours_doctor`, `hours_holidays`
- Computed (stored): `hours_project_total`, `hours_leave_total`, `hours_total`
- Related (stored): `wage_hm`, `wage_ccp`
- Computed costs (stored): `gross_salary = hours_total × wage_hm`, `deductions = gross_salary × 0.362`, `total_labor_cost = hours_total × wage_ccp`
- `leave_auto_synced` — flag set when hr_holidays fills leave hours
- Constraint: `UNIQUE(assignment_id, period)`

### `tenenet.employee.tenenet.cost`
- `employee_id`, `period`
- Manual inputs: `gross_salary_employee`, `total_labor_cost_employee`
- Computed (stored): `project_billed_gross`, `project_billed_ccp` — SUMs from all timesheets for employee+period
- Computed (stored): `tenenet_residual_hm = gross_salary_employee − project_billed_gross`
- Computed (stored): `tenenet_residual_ccp = total_labor_cost_employee − project_billed_ccp`
- Constraint: `UNIQUE(employee_id, period)`

### `hr.leave` override
- `action_validate` → calls `_sync_tenenet_timesheets()`
- For each validated leave, finds active assignments for the employee
- Checks `tenenet.project.leave.rule` per project
- If `included=True`: updates corresponding timesheet leave field
- Calls `tenenet.employee.tenenet.cost._sync_for_employee_period()` after

## Leave Type → Field Mapping (`_leave_type_to_field`)

| Pattern in leave type name | Timesheet field |
|----------------------------|----------------|
| dovolenk / vacation / annual | `hours_vacation` |
| pn / ocr / sick / chorob | `hours_sick` |
| lekar / doctor / medical | `hours_doctor` |
| sviat / holiday / public | `hours_holidays` |

## Views

| File | Content |
|------|---------|
| `views/tenenet_project_timesheet_views.xml` | List (editable), form, search, pivot, graph + action |
| `views/tenenet_employee_tenenet_cost_views.xml` | List, form, search + action |
| `views/tenenet_project_views.xml` | Timesheety tab (editable inline list), Priradenia tab, Pravidlá dovolenky tab |
| `views/menu.xml` | Timesheety under Projekty; Tenenet náklady under Konfigurácia |

## Data Flow

```
User fills timesheet hours in project form (Timesheety tab)
    → hours_total, gross_salary, total_labor_cost computed
    → tenenet.employee.tenenet.cost auto-created/updated for employee+period
    → tenenet.utilization recomputes (via @api.depends on assignment_ids.timesheet_ids)
    → tenenet.pl.line recomputes (via @api.depends on assignment_ids.timesheet_ids)
    → tenenet.employee.tenenet.cost residual recomputes

Odoo hr_holidays leave approved (action_validate)
    → _sync_tenenet_timesheets() called
    → active assignments found for employee
    → leave rule checked per project
    → timesheet leave field updated if included=True
    → residual recomputed
```

## Tests

- `test_plan09_project_timesheet.py`
  - Computed hour totals (project, leave, total)
  - Computed costs (gross, deductions, CCP)
  - Wage inherited from assignment
  - Related fields from assignment
  - Unique constraint on assignment+period
  - Multiple periods allowed
  - Zero hours → zero cost
  - Residual computation
  - Utilization aggregate from timesheets

## Enhancement Note (2026-03-17)

- Hour categories are now normalized in `tenenet.project.timesheet.line` and aggregated back to the parent `tenenet.project.timesheet` record.
- Existing parent fields such as `hours_pp`, `hours_np`, `hours_vacation`, and cost totals remain the compatibility surface for downstream logic and tests.
- A dedicated `Mesačná mriežka hodín` action now provides month-oriented navigation over normalized hour rows using list + pivot views.

## Status: ✅ IMPLEMENTED
