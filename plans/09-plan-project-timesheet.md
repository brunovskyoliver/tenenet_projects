# Plan 09: Project Timesheet Matrix & Tenenet Residual

Monthly timesheet entry per employee-project assignment, replacing `tenenet.employee.allocation`. Includes automatic Tenenet residual cost generation and `hr_holidays` leave auto-sync.

---

## Scope

- `tenenet.project.timesheet` — monthly hours per assignment (replaces `tenenet.employee.allocation`)
- `tenenet.employee.tenenet.cost` — auto-generated residual (salary not covered by projects)
- `hr.leave` override — auto-populate timesheet leave hours from approved Odoo leaves
- Editable inline list view inside project form (Timesheety tab)
- Editable yearly monthly matrix for assignment-based hour entry
- Precreated monthly timesheets generated from assignment/project date range
- Employee-facing dashboard entry for selecting project assignment and filling hours

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
| `views/tenenet_project_timesheet_views.xml` | List (editable), form, search, graph + action |
| `models/tenenet_project_timesheet_matrix.py` | Persistent yearly matrix models (`assignment + year`) with Jan-Dec inverse editing |
| `views/tenenet_project_timesheet_matrix_views.xml` | Full-screen yearly matrix list/form/search |
| `views/tenenet_employee_tenenet_cost_views.xml` | List, form, search + action |
| `views/tenenet_project_assignment_views.xml` | Assignment button/action to open current-year matrix; employee app entry list |
| `views/tenenet_project_views.xml` | Timesheety tab + button to open project-filtered matrix list |
| `views/menu.xml` | `Moje timesheety` dashboard app + `Mesačná matica hodín` under Projekty |

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
- Monthly `tenenet.project.timesheet` parent records are precreated automatically when an assignment has a usable project/assignment date range.
- A persistent `Mesačná matica hodín` now exists per `priradenie + rok`; rows are fixed hour categories and columns are Jan-Dec.
- Users no longer create a wizard record. They open an existing full-screen matrix and edits write directly back into normalized `tenenet.project.timesheet.line` records and parent monthly timesheets.
- The `Moje timesheety` dashboard app opens the current user's project assignments so the employee can choose a project and open the current-year matrix directly.

## Status: ✅ IMPLEMENTED
