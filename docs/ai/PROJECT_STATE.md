# PROJECT_STATE.md — Canonical Project State for AI Agents

Last updated after:

```text
S1.1D Activity Reports / Exports Data Assembly Extraction — VALIDATED
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
feat/s1.1d-activity-report-export-extraction
```

## Current canonical HEAD

```text
1c854f6 S1.1D activity report export data extraction
```

## Current test baseline

S1.1D VALIDATED.

```text
40 activity service tests passed (tests/unit/test_activity_service.py)
5 export layout regression tests passed (test_export_rapoarte_stil)
246 tenant tests passed
127 targeted/regression/smoke tests passed
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
S1.1C Activity Workflow Transition Extraction
S1.1D Activity Reports / Exports Data Assembly Extraction
```

Latest completed service extraction step:

```text
S1.1D Activity Reports / Exports Data Assembly Extraction
```

S1.1D summary:

```text
- added get_activity_rows_for_period() to services/activity_service.py
- added get_timesheet_hours_map_for_period()
- added get_project_activity_report_data()
- extracted tenant-safe data assembly from raport_saptamanal, raport_lunar,
  raport_anual, raport_proiect
- preserved T1.C14 monthly timesheet scoping via query_timesheets_for_tenant()
- left export_edifico and export_edifico_preview in routes intentionally for
  layout stability
- left layout/styling helpers in routes intentionally
- no schema changes
- no migrations
- no template changes
- no Excel/PDF/HTML layout changes
- no file name changes
- no save/workflow/read-context changes
- no Pontaj/BIM/Contract/Gantt/HR/Fleet changes
- no S1.2 started
```

The S1.1 activity service boundary (S1.1A–S1.1D) is functionally complete and
awaits the S1.C1 review.

---

## Current task

```text
S1.C1 Activity Service Extraction Review
```

This is the review checkpoint over the completed S1.1 activity service boundary
(S1.1A read/form context, S1.1B create/edit save, S1.1C workflow transitions,
S1.1D report/export data assembly).

S1.2 TIMESHEET SERVICE EXTRACTION IS NOT YET AUTHORIZED. It may start only after
S1.C1 reviews and approves the completed S1.1 activity service boundary.

## Constraints for the S1.x service extraction line (per D014)

- Extract activity behavior only.
- No schema changes.
- Preserve workflows and statuses.
- MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use tenant_access.py helpers.
- No raw RaportActivitate/Pontaj/Proiect/Angajat/BIM lookups.
- Add direct service-level tests.

## Remaining service extraction work (NOT authorized yet)

```text
S1.C1 Activity Service Extraction Review (current)
S1.2 Timesheet Service Extraction (after S1.C1 approval)
```

Accepted deferral (documented in S1.1D): export_edifico / export_edifico_preview
and their data helpers remain route-resident because those data helpers are
co-called by layout helpers; they are already tenant-safe.

---

## Current repository posture

Route-level tenant guard complete after T1.14.
Activity service boundary covers read/form context (S1.1A), create/edit save (S1.1B), workflow transitions (S1.1C), and report/export data assembly (S1.1D).

Remaining accepted future categories:

```text
service-boundary hardening
historical data contamination cleanup
schema improvements for indirect ownership models
direct service tests for extracted services
```
