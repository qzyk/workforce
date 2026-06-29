# PROJECT_STATE.md — Canonical Project State for AI Agents

Last updated after:

```text
S1.2D1 Timesheet Monthly Export Data Assembly Extraction
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
feat/s1.2d1-timesheet-export-data-extraction
```

## Current canonical HEAD

```text
fc73246 S1.2D1 timesheet export data extraction
```

## Current test baseline

S1.2D1 VALIDATED.

```text
service unit tests (tests/unit/test_timesheet_service.py): 71 passed (59 prior + 12 new S1.2D1)
targeted suite (service + tenant_access_timesheets + integration timesheet routes): 100 passed
export-layout regression (test_export_rapoarte_stil.py): 5 passed
activity boundary (test_activity_service.py): 40 passed
Flask app smoke (pontaje routes): ok 18
full suite (tests/unit + tests/integration): 1117 passed, 39 skipped, 4 warnings
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
S1.2C2 Timesheet Bulk Workflow Extraction
S1.2D1 Timesheet Monthly Export Data Assembly Extraction
```

Latest completed service extraction step:

```text
S1.2D1 Timesheet Monthly Export Data Assembly Extraction
```

S1.2D1 summary:

```text
- build_monthly_timesheet_export_data() added to services/timesheet_service.py
- export_lunar delegates tenant-scoped query, month/year filter, project filter,
  per-employee grouping/totals, holiday day-set, and sorted employees to the service
- workbook layout remains route-owned and unchanged (sheets/order/styles/fills/
  borders/merged cells/formulas/widths/freeze panes/auto_filter/date-day order)
- send_file remains route-owned and unchanged
- filename and MIME behavior preserved
- export helper is read-only and HTTP-free
- no db.session.add/commit/rollback in export helper
- query_timesheets_for_tenant preserved
- get_project_or_404 behavior preserved for foreign project 404
- SarbatoareLegala.query remains allowed as global catalog behavior
- no raw Pontaj/Angajat/Proiect/RaportActivitate.query introduced in service
- get_project_or_404 removed from routes/pontaje.py imports (now only in service)
- template_import untouched
- import_excel untouched
- no S1.2D2 started
- single/bulk workflow untouched
- save/create/edit untouched
- read/list/context untouched
- sterge untouched
- services/activity_service.py untouched
- routes/activitati.py untouched
- models.py untouched
- migrations untouched
- templates untouched
```

Files changed in fc73246:

```text
routes/pontaje.py
services/timesheet_service.py
tests/unit/test_timesheet_service.py
```

Prior S1.2C2 summary (bulk_approve_timesheets, aproba_multiplu delegation,
off-mode Pontaj.query.get legacy branch, fail-all abort(404), service-commit /
route-rollback) remains valid and untouched by S1.2D1.

The S1.1 activity service boundary (S1.1A–S1.1D) is complete and APPROVED by the
S1.C1 review (no P0/P1 blockers).
The S1.2A timesheet service read/list/context boundary is complete and validated.
The S1.2B1 timesheet single create/edit save boundary is complete and validated.
The S1.2B2 timesheet bulk create save boundary is complete and validated.
The S1.2C1 timesheet single workflow (trimite/aproba/respinge) is complete and validated.
The S1.2C2 timesheet bulk workflow (aproba_multiplu) is complete and validated.
The S1.2D1 timesheet monthly export data assembly (build_monthly_timesheet_export_data) is complete and validated.

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
S1.2D2 No-Code Understanding / Collision Safety Gate
```

Read-only understanding/collision-safety gate for the import_excel
parsing/create extraction after S1.2D1. Produces an understanding report only.

S1.2D2 IMPLEMENTATION IS NOT YET AUTHORIZED. It may start only after this
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
S1.2D2 No-Code Understanding / Collision Safety Gate (current)
S1.2D2 Import Excel Parsing/Create Extraction (after gate approval)
```

template_import remains route-resident unless a future explicit task says
otherwise (static workbook layout, no tenant data, no domain logic to extract —
per the S1.2D gate analysis).

Accepted deferral (D015): export_edifico / export_edifico_preview and their data
helpers remain route-resident because those data helpers are co-called by layout
helpers; they are already tenant-safe.

---

## Current repository posture

Route-level tenant guard complete after T1.14.
Activity service boundary covers read/form context (S1.1A), create/edit save (S1.1B), workflow transitions (S1.1C), and report/export data assembly (S1.1D).
Timesheet service boundary now covers read/list/context and pure hour
calculation (S1.2A), single Pontaj create/edit saves (S1.2B1), bulk
Pontaj create saves (S1.2B2), single workflow transitions trimite/aproba/respinge
(S1.2C1), bulk workflow aproba_multiplu (S1.2C2), and monthly export data
assembly for export_lunar (S1.2D1). The export_lunar workbook layout + send_file
stay route-owned. import_excel parsing/create remains intentionally route-resident
pending the S1.2D2 gate + approval; template_import stays route-resident (static
layout, no extraction).

Remaining accepted future categories:

```text
service-boundary hardening
historical data contamination cleanup
schema improvements for indirect ownership models
direct service tests for extracted services
```
