# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.C2 Timesheet Service Extraction Review
```

This is a REVIEW / NO-CODE validation task.

NO NEW IMPLEMENTATION IS AUTHORIZED.

S1.C2 reviews the completed S1.2 timesheet service boundary after:

```text
S1.2A  Timesheet Service Skeleton + Read/List Context Extraction
S1.2B1 Timesheet Single Create/Edit Save Extraction
S1.2B2 Timesheet Bulk Create Save Extraction
S1.2C1 Timesheet Single Workflow Extraction
S1.2C2 Timesheet Bulk Workflow Extraction
S1.2D1 Timesheet Monthly Export Data Assembly Extraction
S1.2D2 Timesheet Import Excel Parsing/Create Extraction
```

Current canonical base commit:

```text
0a7da26 S1.2D2 timesheet import excel extraction
```

Current canonical branch:

```text
feat/s1.2d2-timesheet-import-excel-extraction
```

---

## Previous completed step (S1.2D2) — VALIDATED

```text
S1.2D2 Timesheet Import Excel Parsing/Create Extraction
```

Verdict: COMPLETE. The import_excel row-processing/create logic was extracted from
routes/pontaje.py into services/timesheet_service.py (import_timesheets_from_rows
+ _detect_import_tip_zi) without touching export_lunar, template_import,
save/create/edit, workflow, read/list/context, or delete logic.

S1.2D2 recorded results:

```text
- import_timesheets_from_rows() added to services/timesheet_service.py
- _detect_import_tip_zi() added to services/timesheet_service.py
- import_excel delegates row-processing/create to the timesheet service
- route still owns request.files, .xlsx extension validation, load_workbook,
  wb.active selection, flash, redirect, and the HTTP boundary
- expected columns preserved (CNP, cod_proiect, data, ora_start, ora_sfarsit,
  tip_zi, observatii)
- string coercion preserved; empty rows skipped silently (not counted as errors)
- bad rows counted as errors; missing/foreign employee/project rows skipped
- foreign employee/project skipped via query_for_tenant() (NEVER abort)
- duplicate rows skipped via query_timesheets_for_tenant()
- date parsing preserved (dd.mm.yyyy and yyyy-mm-dd)
- imported rows preserve status='draft'; approval/workflow fields untouched
- partial-success preserved; ONE final commit after the row loop
- NO tenant_id_for_new_record_or_403() and NO require_timesheet_inputs_same_tenant()
  introduced in the import path (would convert skip into abort(404))
- no raw Pontaj/Angajat/Proiect/RaportActivitate.query introduced in service
- SarbatoareLegala.query allowed only as global catalog for tip_zi detection
- route rollback wrapper added without changing per-row skip behavior
- export_lunar / build_monthly_timesheet_export_data / template_import untouched
- save/create/edit / workflow / read/list/context / sterge untouched
- services/activity_service.py / routes/activitati.py untouched
- models.py / migrations / templates untouched
```

S1.2D2 validation:

```text
service unit tests (test_timesheet_service.py): 87 passed (71 prior + 16 new)
full suite (tests/unit + tests/integration): 1133 passed, 39 skipped, 4 warnings
full suite was run BEFORE commit
worktree clean after commit; git diff --check clean
only allowed files changed
```

Files changed in 0a7da26:

```text
routes/pontaje.py
services/timesheet_service.py
tests/unit/test_timesheet_service.py
```

Test-cleanup robustness note (S1.2D2):

```text
- tests/unit/test_timesheet_service.py fixture _curata was hardened to also delete
  Pontaj rows attached to S12A employees/projects, not only rows with observatii
  like 'TEST_S12A%'.
- Reason: import-created Pontaj rows may have arbitrary observatii (empty string,
  'concediu', etc.), so the previous cleanup filter could leave orphan Pontaj rows
  before the test employees/projects were deleted.
- Test-cleanup robustness change only; behavior-preserving and validated by the full suite.
```

---

## Goal of the current task (S1.C2 review)

Review the completed S1.2 timesheet service boundary (NO code):

```text
1. Review services/timesheet_service.py as a complete Pontaj/timesheet service boundary.
2. Verify routes/pontaje.py delegates the intended slices (read/list/context,
   save/create/edit, single+bulk workflow, monthly export data, import rows).
3. Verify tenant safety was preserved across off / optional / strict modes.
4. Verify no raw tenant-owned queries (Pontaj/Angajat/Proiect/RaportActivitate.query)
   were introduced in the service (SarbatoareLegala.query global catalog is allowed).
5. Verify save / workflow / import / export behavior was preserved.
6. Verify the service-commit / route-rollback convention is consistent.
7. Verify tests are sufficient.
8. Identify any P0/P1 blockers.
9. If no P0/P1 blockers, approve S1.2 and recommend the next architectural step.
10. Produce a report only — no code.
```

---

## No-touch boundaries for the S1.C2 review

```text
- do not modify code
- do not modify tests
- do not modify routes
- do not modify services
- do not modify models / migrations / templates
- do not start S1.3
- do not start any new service extraction
- do not touch activity service / routes
- do not alter completed S1.2 helpers
```

---

## Do not start

Do not start any new implementation. The current authorized task is ONLY the
S1.C2 review (report only). Any follow-up implementation requires a separate
explicit approval from Albert.
