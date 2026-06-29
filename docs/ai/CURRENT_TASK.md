# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.2D No-Code Understanding / Collision Safety Gate
```

This is a READ-ONLY understanding and collision-safety gate for the export/import
extraction slice after S1.2C2. It produces an understanding/collision-safety
report only.

IMPORTANT: S1.2D IMPLEMENTATION IS NOT YET AUTHORIZED.
S1.2D implementation may start only after this no-code safety gate is reviewed
and approved by Albert.

Current canonical base commit:

```text
a3f621e S1.2C2 timesheet bulk workflow extraction
```

Current canonical branch:

```text
feat/s1.2c2-timesheet-bulk-workflow-extraction
```

---

## Previous completed step (S1.2C2) — VALIDATED

```text
S1.2C2 Timesheet Bulk Workflow Extraction
```

Verdict: COMPLETE. The bulk Pontaj workflow function (aproba_multiplu) was
extracted from routes/pontaje.py into services/timesheet_service.py without
touching single workflow, save/create/edit, read/list/context, delete, or
export/import logic.

S1.2C2 recorded results:

```text
- bulk_approve_timesheets() added to services/timesheet_service.py
- aproba_multiplu POST delegates to bulk_approve_timesheets()
- get_tenant_mode removed from routes/pontaje.py imports (no longer used there)
- service is HTTP-free; service commits, route rollbacks on exception
- off-mode legacy branch preserved: Pontaj.query.get isolated, documented,
  tested (T1.4 pattern)
- tenant-aware fail-all validation preserved: abort(404) before any mutation
- status == 'trimis' filter preserved
- status mutation, aprobat_de, data_aprobare preserved
- one db.session.commit() after the loop
- count computation preserved
- flash message and redirect unchanged
- single workflow (trimite/aproba/respinge) untouched
- save/create/edit untouched
- read/list/context untouched
- delete route untouched
- export/import untouched
- services/activity_service.py untouched
- routes/activitati.py untouched
- models.py untouched
- migrations untouched
- templates untouched
```

S1.2C2 validation:

```text
py_compile passed
tests/unit/test_timesheet_service.py: 59 passed (43 prior + 16 new S1.2C2)
unit + integration (529 tests): 529 passed
Flask app smoke (pontaje routes): ok 18
git diff --check clean
```

---

## Goal of the current gate (S1.2D no-code)

Prove understanding of the safe boundary for S1.2D BEFORE any code:

1. Confirm canonical worktree state (clean, HEAD a3f621e).
2. Review export_lunar, template_import, import_excel in routes/pontaje.py.
3. Identify what is safe vs risky for extraction.
4. Map no-touch surfaces: all extracted workflow/save/read functions.
5. Produce a non-overlap / hunk-safety plan.
6. End by requiring Albert's explicit approval before coding.

Note: export_edifico/export_edifico_preview were already accepted as deferred
in D015 (layout-sensitive, already tenant-safe). S1.2D concerns only
pontaje export/import.

The gate must NOT modify code, tests, services, or routes.

---

## Do not start

Do not start implementation of:

```text
S1.2D Timesheet Export/Import Extraction
```

The current authorized task is ONLY the S1.2D no-code understanding /
collision-safety gate. Implementation requires a separate explicit approval.
