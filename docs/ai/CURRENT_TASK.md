# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.2D2 No-Code Understanding / Collision Safety Gate
```

This is a READ-ONLY understanding and collision-safety gate for the import_excel
parsing/create extraction slice after S1.2D1. It produces an understanding /
collision-safety report only.

IMPORTANT: S1.2D2 IMPLEMENTATION IS NOT YET AUTHORIZED.
S1.2D2 implementation may start only after this no-code safety gate is reviewed
and approved by Albert.

Current canonical base commit:

```text
fc73246 S1.2D1 timesheet export data extraction
```

Current canonical branch:

```text
feat/s1.2d1-timesheet-export-data-extraction
```

---

## Previous completed step (S1.2D1) — VALIDATED

```text
S1.2D1 Timesheet Monthly Export Data Assembly Extraction
```

Verdict: COMPLETE. The monthly Pontaj export data assembly was extracted from
routes/pontaje.py::export_lunar into services/timesheet_service.py
(build_monthly_timesheet_export_data) without touching the workbook layout,
send_file, filename/MIME behavior, template_import, import_excel, or any
save/workflow/read/delete logic.

S1.2D1 recorded results:

```text
- build_monthly_timesheet_export_data() added to services/timesheet_service.py
- export_lunar delegates tenant-scoped query, month/year filter, project filter,
  per-employee grouping/totals, holiday day-set, and sorted employees to service
- export_lunar still owns: request.args reading, workbook creation, sheet
  names/order, styles, fills, borders, merged cells, formulas, widths, freeze
  panes, auto_filter, date/day order, filename, MIME type, send_file
- export helper is read-only and HTTP-free
- no db.session.add/commit/rollback in export helper
- query_timesheets_for_tenant preserved
- get_project_or_404 behavior preserved for foreign project 404
- SarbatoareLegala.query allowed as global catalog behavior
- no raw Pontaj/Angajat/Proiect/RaportActivitate.query introduced in service
- get_project_or_404 removed from routes/pontaje.py imports (now only in service)
- template_import untouched
- import_excel untouched
- no S1.2D2 started
- services/activity_service.py untouched
- routes/activitati.py untouched
- models.py untouched
- migrations untouched
- templates untouched
```

S1.2D1 validation:

```text
service unit tests (test_timesheet_service.py): 71 passed (59 prior + 12 new)
targeted suite (service + tenant_access_timesheets + integration routes): 100 passed
export-layout regression (test_export_rapoarte_stil.py): 5 passed
activity boundary (test_activity_service.py): 40 passed
Flask app smoke (pontaje routes): ok 18
full suite (tests/unit + tests/integration): 1117 passed, 39 skipped, 4 warnings
git diff --check clean
```

Files changed in fc73246:

```text
routes/pontaje.py
services/timesheet_service.py
tests/unit/test_timesheet_service.py
```

---

## Goal of the current gate (S1.2D2 no-code)

Prove understanding of the safe boundary for the import_excel extraction BEFORE
any code:

1. Confirm canonical worktree state (clean, HEAD fc73246).
2. Understand import_excel upload / parsing / current row handling.
3. Understand the expected Excel columns.
4. Understand duplicate skip/error behavior.
5. Understand tenant-safe employee/project resolution
   (query_for_tenant(Angajat), query_for_tenant(Proiect),
   query_timesheets_for_tenant() duplicate check).
6. Understand partial-success semantics (per-row try/except, count_ok/count_err).
7. Understand the single db.session.commit() behavior at the end of the loop.
8. Understand the current lack of an outer rollback wrapper.
9. Propose a safe extraction boundary for the import row-processing/create logic
   into services/timesheet_service.py.
10. Preserve route-owned upload handling, .xlsx validation, workbook read, flash,
    and redirect behavior.
11. Produce a report only — no code.

The gate must NOT modify code, tests, services, or routes.

---

## No-touch boundaries for the S1.2D2 gate

```text
- do not touch export_lunar (read only for context)
- do not touch workbook layout
- do not touch send_file
- do not touch template_import unless the gate determines no extraction
- do not touch save/create/edit routes
- do not touch workflow routes
- do not touch sterge
- do not touch activity files (service/routes/tests)
- do not touch models / migrations / templates
- do not touch other route domains
```

---

## Do not start

Do not start implementation of:

```text
S1.2D2 Import Excel Parsing/Create Extraction
```

The current authorized task is ONLY the S1.2D2 no-code understanding /
collision-safety gate. Implementation requires a separate explicit approval.
