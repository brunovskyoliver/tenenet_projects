# Tenenet Projects — Master Implementation Plan

High-level roadmap for building the Tenenet Odoo v19 module suite.

---

## Module Dependency Graph

```
tenenet.program (independent)
tenenet.donor (independent)
       │
       ├──→ hr.employee extension (depends: hr)
       │
       └──→ tenenet.project (depends: program, donor, employee)
                │
                ├──→ tenenet.project.assignment (depends: project, employee)
                │         │
                │         └──→ tenenet.project.leave.rule (depends: assignment, hr.leave.type)
                │         └──→ tenenet.project.timesheet (depends: assignment)
                │                   │
                │                   ├──→ tenenet.utilization [COMPUTED] (depends: employee)
                │                   ├──→ tenenet.pl.line [COMPUTED] (depends: employee, program)
                │                   └──→ tenenet.employee.tenenet.cost (depends: employee)
                │
                └──→ tenenet.employee.allocation [SUPERSEDED — read-only archive]
```

---

## Implementation Phases

### Phase 1: Foundation (Models + Security)

| Step | Plan File | Models | Priority |
|------|-----------|--------|----------|
| 1.1 | `01-plan-employee.md` | `hr.employee` extension, `tenenet.program`, `tenenet.donor` | HIGH |
| 1.2 | `02-plan-project.md` | `tenenet.project` | HIGH |
| 1.3 | `07-plan-security-access.md` | Groups, ACL, record rules | HIGH |

**Deliverables**: All core models created, security in place, basic list/form views.

### Phase 2: Data Layer (Assignments + Timesheets + Utilization)

| Step | Plan File | Models | Priority |
|------|-----------|--------|----------|
| 2.1 | `03-plan-allocation.md` | `tenenet.employee.allocation` — **SUPERSEDED** | ARCHIVE |
| 2.2 | `04-plan-utilization.md` | `tenenet.utilization` — **UPDATED** (now computed) | ARCHIVE |
| 2.3 | `08-plan-project-assignment.md` | `tenenet.project.assignment`, `tenenet.project.leave.rule` | HIGH ✅ |
| 2.4 | `09-plan-project-timesheet.md` | `tenenet.project.timesheet`, `tenenet.employee.tenenet.cost`, `hr.leave` override | HIGH ✅ |
| 2.5 | `10-plan-utilization-computed.md` | `tenenet.utilization` as computed aggregate | HIGH ✅ |

**Deliverables**: Junction models for employee-project allocations, utilization tracking with computed KPIs.

### Phase 3: Reporting

| Step | Plan File | Models | Priority |
|------|-----------|--------|----------|
| 3.1 | `05-plan-pl-reporting.md` | `tenenet.pl.line` | MEDIUM |

**Deliverables**: P&L lines, pivot views, allocation key computations.

### Phase 4: Data Migration

| Step | Plan File | Components | Priority |
|------|-----------|------------|----------|
| 4.1 | `06-plan-data-migration.md` | Import wizards for all Excel files | MEDIUM |

**Deliverables**: Working import wizards for all 4 Excel files, validation reports.

### Phase 5: Polish

- Dashboard views (kanban, pivot, graph)
- QWeb PDF reports
- Translations (Slovak)
- Performance optimization
- Full test suite

---

## Success Criteria

- [ ] All 7 models created and functional
- [ ] List, form, search views for every model
- [ ] Menu structure: Tenenet → Projects / Employees / Reporting / Configuration
- [ ] Security: User (read) vs Manager (full CRUD)
- [ ] Excel import wizards for all 4 source files
- [ ] Computed fields match Excel formulas
- [ ] Unit tests for all computed fields and constraints
- [ ] Data imported from migration files without errors

---

## Key References

| Document | Location |
|----------|----------|
| Data Model | `docs/data-model.md` |
| Relations | `docs/data-relations.md` |
| Excel Mapping | `docs/excel-column-mapping.md` |
| Implementation Guide | `docs/implementation-guide.md` |
| Glossary | `docs/glossary-sk.md` |
| Agent Instructions | `tenenet_projects/AGENTS.md` |
| Odoo v19 Skills | `.windsurf/skills/odoo-19/references/` |
