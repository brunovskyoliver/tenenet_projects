# Plan 07: Security & Access Control

Groups, ACL rules, and record rules for the Tenenet module.

---

## Scope

- Security groups (User, Manager)
- Access rights (ir.model.access.csv)
- Record rules (optional — for multi-company or data isolation)

## Tasks

### 1. Create Module Category & Groups
- **File**: `security/tenenet_security.xml`
- **Category**: Tenenet (ir.module.category)
- **Groups**:
  - `group_tenenet_user` — Read access to all models, write to allocations
  - `group_tenenet_manager` — Full CRUD on all models; implied by user group

### 2. Access Control List
- **File**: `security/ir.model.access.csv`
- **Rules per model**:

| Model | User | Manager |
|-------|------|---------|
| tenenet.program | R | RWCD |
| tenenet.donor | R | RWCD |
| tenenet.project | RW | RWCD |
| tenenet.employee.allocation | R | RWCD |
| tenenet.utilization | R | RWCD |
| tenenet.pl.line | R | RWCD |
| Import wizards | — | RWCD |

### 3. Record Rules (Optional)
- Consider: Project managers can only edit their own projects
- Consider: Employees can only view their own allocations/utilization
- Implement if needed after core functionality works

### 4. Wizard Access
- Import wizards should only be accessible to managers
- Add `groups="tenenet_projects.group_tenenet_manager"` to wizard menu items

### 5. Tests
- Verify user group can read but not write programs/donors
- Verify manager group has full access
- Test wizard access restriction

## References
- `references/odoo-19-security-guide.md` — ACL, record rules, groups
- `docs/implementation-guide.md` → Phase 5: Security Setup
