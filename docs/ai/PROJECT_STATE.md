# PROJECT_STATE.md — Canonical Project State for AI Agents

Last updated after:

```text
S1.2B2 Timesheet Bulk Create Save Extraction
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
feat/s1.2c1-timesheet-single-workflow-extraction
```

## Current canonical HEAD

```text
d1bde5f4d6e53aa8a0b17a99aaf8e2bfd1e48a45 S1.2C1 timesheet single workflow extraction
```

## Current test baseline

S1.2C1 VALIDATED.

```text
py_compile passed
tests/unit/test_timesheet_service.py: 43 passed (36 prior + 7 new S1.2C1)
unit + integration (490 tests): 490 passed
git diff --check clean
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

T1.C14 APPROVED. Tenant guard phase complete.

---

## Completed service extraction steps

```text
S1.1A Activity Service Skeleton + Read/Form Context Extraction
S1.1B Activity Create/Edit Save Extraction
S1.1C Activity Workflow Transition Extraction
S1.1D Activity Reports / Exports Data Assembly Extraction
S1.2A Timesheet Service Skeleton + Read/List Context Extraction
S1.2B1 Timesheet Single Create/Edit Save Extraction
S1.2B2 Timesheet Bulk Create Save Extraction
S1.2C1 Timesheet Single Workflow Extraction
```

Latest completed service extraction step:

```text
S1.2C1 Timesheet Single Workflow Extraction
```

S1.2C1 summary:

```text
- submit_timesheet_for_approval() added to services/timesheet_service.py
- approve_timesheet() added to services/timesheet_service.py
- reject_timesheet() added to services/timesheet_service.py
- trimite POST delegates to submit_timesheet_for_approval()
- aproba POST delegates to approve_timesheet()
- respinge POST delegates to reject_timesheet()
- service is HTTP-free; service commits, route rollbacks on exception
- submit_timesheet_for_approval no-ops without commit if status != 'draft'
- reject_timesheet preserves empty reason string exactly
- no data fields (ore_lucrate, ora_start, ora_sfarsit, observatii) modified
- raw-query guard test added and passes
- aproba_multiplu bulk workflow untouched (target of S1.2C2)
- export/import untouched
- services/activity_service.py untouched
- routes/activitati.py untouched
- models.py untouched
- migrations untouched
- templates untouched
```

The S1.1 activity service boundary (S1.1A–S1.1D) is complete and APPROVED by the
S1.C1 review (no P0/P1 blockers).
The S1.2A timesheet service read/list/context boundary is complete and validated.
The S1.2B1 timesheet single create/edit save boundary is complete and validated.
The S1.2B2 timesheet bulk create save boundary is complete and validated.
The S1.2C1 timesheet single workflow (trimite/aproba/respinge) is complete and validated.

---

## Review checkpoints

```text
S1.C1 Activity Service Extraction Review — APPROVED (no P0/P1)
```

S1.C1 findings (see DECISIONS_LOG D015):

```text
- P2: standardize the commit/rollback ownership convention during/around S1.2
      (service currently commits, route wrapper owns rollback)
- P2: S1.2 timesheet must use a NEW file services/timesheet_service.py,
      not services/activity_service.py
- P3: export_edifico/export_edifico_preview intentionally deferred in routes
- P3: sterge (activity delete) unextracted and acceptable
```

---

## Current task

```text
S1.2C2 No-Code Understanding / Collision Safety Gate
```

Read-only understanding/collision-safety gate for the aproba_multiplu bulk
workflow extraction slice after S1.2C1. Produces an understanding report only.

S1.2C2 IMPLEMENTATION IS NOT YET AUTHORIZED. It may start only after this
no-code safety gate is reviewed and approved by Albert.

## Constraints for the S1.x service extraction line (per D014 + D015)

- Extract one domain's behavior only.
- No schema changes.
- Preserve workflows and statuses.
- MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use tenant_access.py helpers.
- No raw RaportActivitate/Pontaj/Proiect/Angajat/BIM lookups in new service code.
- Add direct service-level tests.
- S1.2 timesheet logic goes in a NEW services/timesheet_service.py (D015).

## Remaining service extraction work (NOT authorized yet)

```text
S1.2C2 No-Code Understanding / Collision Safety Gate (current)
S1.2C2 Timesheet Bulk Workflow Extraction (aproba_multiplu, after gate is approved)
S1.2D Timesheet Export/Import Extraction
```

Accepted deferral (D015): export_edifico / export_edifico_preview and their data
helpers remain route-resident because those data helpers are co-called by layout
helpers; they are already tenant-safe.

---

## Current repository posture

Route-level tenant guard complete after T1.14.
Activity service boundary covers read/form context (S1.1A), create/edit save (S1.1B), workflow transitions (S1.1C), and report/export data assembly (S1.1D).
Timesheet service boundary now covers read/list/context and pure hour
calculation (S1.2A), single Pontaj create/edit saves (S1.2B1), bulk
Pontaj create saves (S1.2B2), and single workflow transitions trimite/aproba/respinge
(S1.2C1). Bulk workflow (aproba_multiplu), export, and import logic remain
intentionally route-resident until later approved slices.

Remaining accepted future categories:

```text
service-boundary hardening
historical data contamination cleanup
schema improvements for indirect ownership models
direct service tests for extracted services
```
