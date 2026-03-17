# Plan 08: Project Assignment & Leave Rules

Employee-to-project assignment model with individual wage rates and per-project hr_holidays leave type rules.

---

## Scope

- `tenenet.project.assignment` — links employee to project with wage_hm and wage_ccp
- `tenenet.project.leave.rule` — per-project allowlist of hr.leave.types

## Prerequisites

- `hr.employee` extension (Plan 01)
- `tenenet.project` (Plan 02)
- `hr_holidays` Odoo module (dependency added to manifest)

## Models

### `tenenet.project.assignment`
- `employee_id`, `project_id`, `date_start`, `date_end`, `wage_hm`, `wage_ccp`, `active`
- Constraint: `UNIQUE(employee_id, project_id)`
- One2many from `tenenet.project` → `assignment_ids`
- One2many from `hr.employee` → `assignment_ids`

### `tenenet.project.leave.rule`
- `project_id`, `leave_type_id` (hr.leave.type), `included`
- Constraint: `UNIQUE(project_id, leave_type_id)`
- One2many from `tenenet.project` → `leave_rule_ids`

## Files

| File | Description |
|------|-------------|
| `models/tenenet_project_assignment.py` | Assignment model |
| `models/tenenet_project_leave_rule.py` | Leave rule model |
| `views/tenenet_project_assignment_views.xml` | List, form, search views + action |
| `views/tenenet_project_views.xml` | Added "Priradenia zamestnancov" and "Pravidlá dovolenky" tabs |
| `views/hr_employee_views.xml` | Added assignment list to TENENET employee tab |
| `views/menu.xml` | Added Priradenia to Konfigurácia menu |
| `security/ir.model.access.csv` | ACL entries for both models |
| `tests/test_plan08_project_assignment.py` | Tests |

## Tests

- Create assignment, verify fields
- Unique constraint on employee+project
- Multiple projects for same employee allowed
- Date validation (start > end raises)
- One2many on employee and project
- ACL: user read-only, manager full CRUD
- Leave rule create, unique constraint

## Status: ✅ IMPLEMENTED
