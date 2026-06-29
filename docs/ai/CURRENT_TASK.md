# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.2C2 No-Code Understanding / Collision Safety Gate
```

This is a READ-ONLY understanding and collision-safety gate for the bulk
workflow extraction slice (aproba_multiplu) after S1.2C1. It produces an
understanding/collision-safety report only.

IMPORTANT: S1.2C2 IMPLEMENTATION IS NOT YET AUTHORIZED.
S1.2C2 implementation may start only after this no-code safety gate is reviewed
and approved by Albert.

Current canonical base commit:

```text
d1bde5f4d6e53aa8a0b17a99aaf8e2bfd1e48a45 S1.2C1 timesheet single workflow extraction
```

Current canonical branch:

```text
feat/s1.2c1-timesheet-single-workflow-extraction
```

---

## Previous completed step (S1.2C1) — VALIDATED

```text
S1.2C1 Timesheet Single Workflow Extraction
```

Verdict: COMPLETE. The three single-Pontaj workflow functions (trimite, aproba,
respinge) were extracted from routes/pontaje.py into services/timesheet_service.py
without touching bulk workflow, export/import, or any other domain.

S1.2C1 recorded results:

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

S1.2C1 validation:

```text
py_compile passed
tests/unit/test_timesheet_service.py: 43 passed (36 prior + 7 new)
unit + integration (490 tests): 490 passed
git diff --check clean
```

---

## Goal of the current gate (S1.2C2 no-code)

Prove understanding of the safe boundary for S1.2C2 BEFORE any code:

1. Confirm canonical worktree state (clean, HEAD d1bde5f).
2. Review aproba_multiplu in routes/pontaje.py — identify all logical branches:
   - off-mode legacy branch (Pontaj.query.get raw — T1.4 pattern)
   - strict/optional tenant branch
   - fail-all-or-nothing semantics
   - commit-once after loop
   - count flash
3. Map no-touch surfaces: single workflow (S1.2C1 done), single save, bulk create,
   read/list context, export/import, templates, models, migrations,
   activity service, activity routes, other domains.
4. Preserve the service-commit / route-rollback convention (S1.2B/C1).
5. Produce a non-overlap / hunk-safety plan for aproba_multiplu only.
6. List the files likely allowed for S1.2C2.
7. End by requiring Albert's explicit approval before coding.

The gate must NOT modify code, tests, services, or routes.

---

## Scope of the eventual S1.2C2 (for reference only — not authorized yet)

When approved, S1.2C2 may extract only aproba_multiplu bulk workflow logic from
routes/pontaje.py into services/timesheet_service.py, per D014 + D015:

- Extract timesheet behavior only.
- Use services/timesheet_service.py (NOT activity_service.py).
- No schema changes.
- Preserve fail-all-or-nothing semantics, commit-once after loop, count flash.
- Preserve off-mode legacy branch (Pontaj.query.get guarded by mode check).
- MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use services/security/tenant_access.py timesheet helpers.
- Preserve the S1.2B service-commit / route-rollback convention.
- Add direct service-level tests.
- Do not start S1.2D export/import extraction.

---

## Do not start

Do not start implementation of:

```text
S1.2C2 Timesheet Bulk Workflow Extraction
```

The current authorized task is ONLY the S1.2C2 no-code understanding /
collision-safety gate. Implementation requires a separate explicit approval.
