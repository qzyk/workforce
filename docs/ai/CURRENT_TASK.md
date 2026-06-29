# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.2B2 No-Code Understanding / Collision Safety Gate
```

This is a READ-ONLY understanding and collision-safety gate for the next
timesheet extraction slice after S1.2B1. It produces an understanding/collision-
safety report only.

IMPORTANT: S1.2B2 IMPLEMENTATION IS NOT YET AUTHORIZED.
S1.2B2 implementation may start only after this no-code safety gate is reviewed
and approved by Albert.

Current canonical base commit:

```text
9ae225ca7ec85dc6e38f92e1db4a8cae4fb2bf71 S1.2B1 timesheet single save extraction
```

Current canonical branch:

```text
feat/s1.2b1-timesheet-single-save-extraction
```

---

## Previous completed step (S1.2B1) — VALIDATED

```text
S1.2B1 Timesheet Single Create/Edit Save Extraction
```

Verdict: COMPLETE. The timesheet service single Pontaj create/edit save boundary
was extracted without starting bulk create, workflow, export, or import
extraction.

S1.2B1 recorded results:

```text
- single Pontaj create/edit save logic extracted to services/timesheet_service.py
- create_timesheet_from_form_data() added
- update_timesheet_from_form_data() added
- adauga valid POST save branch delegates to timesheet service
- editeaza valid POST save branch delegates to timesheet service
- duplicate handling remains tenant-scoped and route-compatible
- foreign employee/project validation preserved
- strict mode fail-closed behavior preserved
- off mode legacy behavior preserved
- create status behavior preserved
- edit status behavior preserved:
  action trimite -> trimis
  otherwise existing status preserved
- service remains HTTP-free
- successful single create/edit saves commit in service
- route keeps flash/redirect/render/rollback behavior
- no adauga_multiplu extraction started
- no workflow extraction started
- no export/import extraction started
- no S1.2C/S1.2D started
- services/activity_service.py untouched
- routes/activitati.py untouched
- models.py untouched
- migrations untouched
- templates untouched
```

S1.2B1 validation:

```text
py_compile passed
targeted timesheet suite: 56 passed
full tenant suite: 246 passed
activity boundary regression: 45 passed
Flask app import smoke: ok 18
git diff --check clean
```

---

## Goal of the current gate (S1.2B2 no-code)

Prove understanding of the safe boundary for S1.2B2 BEFORE any code:

1. Confirm canonical worktree state (clean, HEAD 9ae225c).
2. Review the S1.2A and S1.2B1 service boundary in services/timesheet_service.py.
3. Identify only bulk Pontaj create logic that may be considered for
   S1.2B2 extraction.
4. Map no-touch surfaces: single save, workflow, export/import, templates, models,
   migrations, activity service, activity routes, and other domains.
5. Preserve the commit/rollback convention established by S1.2B1.
6. Produce a non-overlap / hunk-safety plan for adauga_multiplu only.
7. List the files likely allowed for S1.2B2.
8. End by requiring Albert's explicit approval before coding.

The gate must NOT modify code, tests, services, or routes.

---

## Scope of the eventual S1.2B2 (for reference only — not authorized yet)

When approved, S1.2B2 may extract only bulk Pontaj create logic from
routes/pontaje.py into services/timesheet_service.py, per D014 + D015:

- Extract timesheet behavior only.
- Use services/timesheet_service.py (NOT activity_service.py).
- No schema changes.
- Preserve single save behavior, workflows, statuses, exports, imports, and layouts.
- MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use services/security/tenant_access.py timesheet helpers.
- No raw Pontaj/Proiect/Angajat/BIM lookups in new service code.
- Preserve the S1.2B1 commit/rollback ownership convention.
- Add direct service-level tests.
- Do not start S1.2C workflow extraction.
- Do not start S1.2D export/import extraction.

---

## Do not start

Do not start implementation of:

```text
S1.2B2 Timesheet Bulk Create Save Extraction
```

The current authorized task is ONLY the S1.2B2 no-code understanding /
collision-safety gate. Implementation requires a separate explicit approval.
