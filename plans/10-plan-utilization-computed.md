# Plan 10: Utilization as Computed Aggregate

Rework `tenenet.utilization` from a manually entered model to one that is fully computed from `tenenet.project.timesheet` records.

---

## Scope

- `tenenet.utilization` — hour fields now computed from timesheet; only `capacity_hours`, `work_ratio`, `manager_id` are manually settable
- `tenenet.pl.line.amount` — computed from timesheet `total_labor_cost` grouped by employee+program+period

## Changes to `tenenet.utilization`

### Fields changed to computed (stored)

| Field | Compute Source |
|-------|---------------|
| `hours_pp` | SUM timesheet.hours_pp for employee+period |
| `hours_np` | SUM timesheet.hours_np for employee+period |
| `hours_travel` | SUM timesheet.hours_travel for employee+period |
| `hours_training` | SUM timesheet.hours_training for employee+period |
| `hours_ambulance` | SUM timesheet.hours_ambulance for employee+period |
| `hours_international` | SUM timesheet.hours_international for employee+period |
| `hours_vacation` | SUM timesheet.hours_vacation for employee+period |
| `hours_doctor` | SUM timesheet.hours_doctor for employee+period |
| `hours_sick` | SUM timesheet.hours_sick for employee+period |

### Fields that remain manually settable

- `capacity_hours` — monthly capacity (from contract/HR)
- `work_ratio` — full-time equivalent ratio
- `manager_id`, `manager_name` — responsible person

### `_compute_from_timesheets` method

```python
@api.depends(
    "employee_id", "period",
    "employee_id.assignment_ids.timesheet_ids.period",
    "employee_id.assignment_ids.timesheet_ids.hours_pp",
    ...
)
def _compute_from_timesheets(self):
    ...
```

All downstream KPI fields remain unchanged:
- `hours_project_total`, `hours_non_project_total`
- `utilization_rate`, `utilization_status`
- `non_project_rate`, `non_project_status`
- `hours_diff`

## Changes to `tenenet.pl.line`

`amount` becomes stored computed from timesheets:
```python
@api.depends("employee_id", "program_id", "period",
             "employee_id.assignment_ids.project_id.program_id",
             "employee_id.assignment_ids.timesheet_ids.period",
             "employee_id.assignment_ids.timesheet_ids.total_labor_cost")
def _compute_amount(self):
    amount = SUM(timesheet.total_labor_cost
                 WHERE employee=self.employee_id
                 AND project.program=self.program_id
                 AND period=self.period)
```

## Utilization Record Creation

Utilization records must exist before computing. Records are created by:
1. Manual creation by manager (as before)
2. Auto-creation via `tenenet.employee.tenenet.cost._sync_for_employee_period()` (called from hr.leave sync)
3. Future: cron job to auto-generate utilization stubs for all employees at period start

## Status: ✅ IMPLEMENTED
