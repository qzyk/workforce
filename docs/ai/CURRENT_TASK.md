# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.2B No-Code Understanding / Collision Safety Gate
```

This is a READ-ONLY understanding and collision-safety gate for the next
timesheet extraction slice after S1.2A. It produces an understanding/collision-
safety report only.

IMPORTANT: S1.2B IMPLEMENTATION IS NOT YET AUTHORIZED.
S1.2B implementation may start only after this no-code safety gate is reviewed
and approved by Albert.

Current canonical base commit:

```text
a7b243c S1.2A timesheet service read context extraction
```

Current canonical branch:

```text
feat/s1.2a-timesheet-service-read-context
```

---

## Previous completed step (S1.2A) — VALIDATED

```text
S1.2A Timesheet Service Skeleton + Read/List Context Extraction
```

Verdict: COMPLETE. The timesheet service read/list/context boundary was created
without starting save, workflow, export, or import extraction.

S1.2A recorded results:

```text
- services/timesheet_service.py created
- low-risk Pontaj read/list/context logic extracted
- calculate_hours behavior preserved through timesheet service boundary
- routes/pontaje.py touched only imports, calculate_hours, lista,
  angajati_proiect, verificare_duplicat, situatie_zilnica, calendar_view,
  aprobare
- services/activity_service.py untouched
- routes/activitati.py untouched
- models.py untouched
- migrations untouched
- templates untouched
- no create/edit Pontaj save extraction started
- no workflow extraction started
- no export/import extraction started
- no S1.2B/S1.2C/S1.2D started
```

S1.2A validation:

```text
44 targeted Pontaj/timesheet tests passed:
- tests/unit/test_timesheet_service.py
- tests/unit/test_tenant_access_timesheets.py
- tests/integration/test_tenant_access_timesheet_routes.py
```

---

## Goal of the current gate (S1.2B no-code)

Prove understanding of the safe boundary for S1.2B BEFORE any code:

1. Confirm canonical worktree state (clean, HEAD a7b243c).
2. Review the S1.2A service boundary in services/timesheet_service.py.
3. Identify only create/edit Pontaj save logic that may be considered for
   S1.2B extraction.
4. Map no-touch surfaces: workflow, export/import, templates, models,
   migrations, activity service, activity routes, and other domains.
5. Decide the commit/rollback convention for save extraction (D015 P2).
6. Produce a non-overlap / hunk-safety plan for adauga, adauga_multiplu,
   and editeaza save paths.
7. List the files likely allowed for S1.2B.
8. End by requiring Albert's explicit approval before coding.

The gate must NOT modify code, tests, services, or routes.

---

## Scope of the eventual S1.2B (for reference only — not authorized yet)

When approved, S1.2B may extract only create/edit Pontaj save logic from
routes/pontaje.py into services/timesheet_service.py, per D014 + D015:

- Extract timesheet behavior only.
- Use services/timesheet_service.py (NOT activity_service.py).
- No schema changes.
- Preserve workflows, statuses, exports, imports, and layouts.
- MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use services/security/tenant_access.py timesheet helpers.
- No raw Pontaj/Proiect/Angajat/BIM lookups in new service code.
- Standardize the commit/rollback ownership convention (D015 P2).
- Add direct service-level tests.
- Do not start S1.2C workflow extraction.
- Do not start S1.2D export/import extraction.

---

## Do not start

Do not start implementation of:

```text
S1.2B Timesheet Create/Edit Save Extraction
```

The current authorized task is ONLY the S1.2B no-code understanding /
collision-safety gate. Implementation requires a separate explicit approval.
