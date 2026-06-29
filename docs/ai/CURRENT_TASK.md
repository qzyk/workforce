# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.2C No-Code Understanding / Collision Safety Gate
```

This is a READ-ONLY understanding and collision-safety gate for the next
timesheet extraction slice after S1.2B2. It produces an understanding/collision-
safety report only.

IMPORTANT: S1.2C IMPLEMENTATION IS NOT YET AUTHORIZED.
S1.2C implementation may start only after this no-code safety gate is reviewed
and approved by Albert.

Current canonical base commit:

```text
12933c59bbc755a933368824565f927b64726b1c S1.2B2 timesheet bulk save extraction
```

Current canonical branch:

```text
feat/s1.2b2-timesheet-bulk-save-extraction
```

---

## Previous completed step (S1.2B2) — VALIDATED

```text
S1.2B2 Timesheet Bulk Create Save Extraction
```

Verdict: COMPLETE. The timesheet service bulk Pontaj create save boundary was
extracted without changing single save, workflow, delete, export, or import
behavior.

S1.2B2 recorded results:

```text
- bulk Pontaj create save logic extracted to services/timesheet_service.py
- create_multiple_timesheets_from_form_data() added
- adauga_multiplu POST bulk save branch delegates to timesheet service
- adauga_multiplu GET behavior unchanged
- duplicate skipping preserved
- count_ok / count_skip behavior preserved as created_count / skipped_count
- zero-selected 0/0 behavior preserved
- tenant validation happens before mutation
- mixed/foreign selected employees fail before mutation
- strict mode fail-closed behavior preserved
- off mode legacy behavior preserved
- status behavior preserved:
  actiune=trimite -> trimis
  otherwise draft
- service remains HTTP-free
- service commits once after the loop
- route keeps flash/redirect/render/rollback behavior
- no single save changes
- no workflow extraction started
- no delete extraction started
- no export/import extraction started
- no S1.2C/S1.2D started
- services/activity_service.py untouched
- routes/activitati.py untouched
- models.py untouched
- migrations untouched
- templates untouched
```

S1.2B2 validation:

```text
py_compile passed
tests/unit/test_timesheet_service.py: 36 passed
targeted timesheet suite: 65 passed
full tenant suite: 246 passed
activity boundary regression: 45 passed
Flask app import smoke: ok 18
git diff --check clean
```

---

## Goal of the current gate (S1.2C no-code)

Prove understanding of the safe boundary for S1.2C BEFORE any code:

1. Confirm canonical worktree state (clean, HEAD 12933c5).
2. Review the S1.2A/S1.2B1/S1.2B2 boundary in services/timesheet_service.py.
3. Identify only Pontaj workflow logic that may be considered for S1.2C
   extraction.
4. Map no-touch surfaces: read/list context, single save, bulk create,
   export/import, templates, models,
   migrations, activity service, activity routes, and other domains.
5. Preserve the service-commit / route-rollback convention established by S1.2B.
6. Produce a non-overlap / hunk-safety plan for workflow routes only.
7. List the files likely allowed for S1.2C.
8. End by requiring Albert's explicit approval before coding.

The gate must NOT modify code, tests, services, or routes.

---

## Scope of the eventual S1.2C (for reference only — not authorized yet)

When approved, S1.2C may extract only Pontaj workflow logic from
routes/pontaje.py into services/timesheet_service.py, per D014 + D015:

- Extract timesheet behavior only.
- Use services/timesheet_service.py (NOT activity_service.py).
- No schema changes.
- Preserve read/list, single save, bulk create, exports, imports, and layouts.
- MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use services/security/tenant_access.py timesheet helpers.
- No raw Pontaj/Proiect/Angajat/BIM lookups in new service code.
- Preserve the S1.2B service-commit / route-rollback convention.
- Add direct service-level tests.
- Do not start S1.2D export/import extraction.

---

## Do not start

Do not start implementation of:

```text
S1.2C Timesheet Workflow Extraction
```

The current authorized task is ONLY the S1.2C no-code understanding /
collision-safety gate. Implementation requires a separate explicit approval.
