# PROJECT_STATE.md — Canonical Project State for AI Agents

Last updated after:

```text
S1.1B Activity Create/Edit Save Extraction — VALIDATED
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
feat/s1.1b-activity-save-extraction
```

## Current canonical HEAD

```text
bc98a29 S1.1B activity save extraction
```

## Current test baseline

S1.1B VALIDATED.

```text
19 activity service tests passed (tests/unit/test_activity_service.py)
61 targeted activity + tenant tests passed
246 tenant tests passed
50 regression/smoke tests passed (models_workforce + export_rapoarte_stil + smoke)
app import OK, 25 activitati routes
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
```

Latest completed service extraction step:

```text
S1.1B Activity Create/Edit Save Extraction
```

S1.1B summary:

```text
- added save_activity_from_form_data() to services/activity_service.py
- added ActivityValidationError
- moved create/edit save parsing, validation, field assignment, JSON
  serialization, BIM context validation, inline save status logic,
  calculeaza_perioada(), and db commit into activity_service
- routes/activitati.py keeps _salveaza_activitate as a thin HTTP wrapper
- route behavior, flash messages, redirects, jsonify shape, approval
  workflow, and exports remain unchanged
- no schema changes
- no migrations
- no workflow route extraction
- no export/report extraction
- no S1.1C/S1.1D/S1.2 started
```

---

## Current task

```text
S1.1C No-Code Understanding / Collision Safety Gate
```

This is a read-only understanding/collision-safety gate for S1.1C (Activity
Workflow Transitions extraction). It produces an understanding report only.

S1.1C IMPLEMENTATION IS NOT YET AUTHORIZED. It may start only after this
no-code safety gate is reviewed and approved by Albert.

## Constraints for the S1.1x service extraction line (per D014)

- Extract activity behavior only.
- No schema changes.
- Preserve workflows and statuses.
- MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use tenant_access.py helpers.
- No raw RaportActivitate/Pontaj/Proiect/Angajat/BIM lookups.
- Add direct service-level tests.

## Remaining activity extraction work (NOT authorized yet)

```text
S1.1C Activity Workflow Transitions
S1.1D Activity Reports/Exports Cleanup
```

---

## Current repository posture

Route-level tenant guard complete after T1.14.
Activity service boundary covers read/form context (S1.1A) and create/edit save (S1.1B).

Remaining accepted future categories:

```text
service-boundary hardening
historical data contamination cleanup
schema improvements for indirect ownership models
direct service tests for extracted services
```
