# PROJECT_STATE.md — Canonical Project State for AI Agents

Last updated after:

```text
T1.C14 Final Tenant Guard Review — APPROVED
```

Canonical repository:

```text
qzyk/workforce
```

Canonical worktree:

```text
/Users/albertciolacu/workforce-t1.5-contract
```

Do not work in:

```text
/Users/albertciolacu/workforce
```

External Claude worktrees:

```text
/Users/albertciolacu/workforce/.claude/worktrees/
```

Status of external Claude worktrees:

```text
External non-authoritative experimental worktrees.
Excluded from canonical reviews and implementation tasks.
Do not merge, clean, delete, or copy from them.
```

---

## Current canonical branch

```text
feat/t1.14-activity-bim-context-tenant-guard
```

## Current canonical HEAD

```text
7329cd7 T1.C14 fix: raport_lunar pontaje tenant-safe
```

## Current test baseline

T1.C14 APPROVED.

```text
246 tenant tests passed
T1.C14 fix: raport_lunar() now uses query_timesheets_for_tenant()
```

---

## Completed tenant guard stack

```text
T1.1  tenant access foundation
T1.2  project tenant guard
T1.3  activity tenant guard
T1.4  timesheet tenant guard
T1.5  contract tenant guard
T1.6  document tenant guard
T1.7  BIM tenant guard
T1.8  Gantt tenant guard
T1.9  dashboard reporting tenant guard
T1.10 HR fleet tenant guard
T1.11 notifications admin tenant guard
T1.12 project nested tenant guard
T1.13 locations audit api tokens tenant guard
T1.14 activity BIM context tenant guard
```

---

## Current task

```text
S1.1 Activity Service Extraction
```

T1.C14 APPROVED. Tenant guard phase complete.

## Constraints for S1.1 (per D014)

- Extract activity behavior only.
- No schema changes.
- Preserve workflows and statuses.
- MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use tenant_access.py helpers.
- No raw RaportActivitate/Pontaj/Proiect/Angajat/BIM lookups.
- Add direct service-level tests.

---

## Current repository posture

Route-level tenant guard complete after T1.14.

Remaining accepted future categories:

```text
service-boundary hardening
historical data contamination cleanup
schema improvements for indirect ownership models
direct service tests for extracted services
```
