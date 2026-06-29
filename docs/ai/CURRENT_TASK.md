# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.2 No-Code Understanding / Collision Safety Gate
```

This is a READ-ONLY understanding and collision-safety gate for the next
extraction step (S1.2 Timesheet Service Extraction). It produces an
understanding/collision-safety report only.

IMPORTANT: S1.2 IMPLEMENTATION IS NOT YET AUTHORIZED.
S1.2 implementation may start only after this no-code safety gate is reviewed
and approved by Albert.

Current canonical base commit:

```text
f840eb7 Update AI coordination state after S1.1D
```

Current canonical branch:

```text
feat/s1.1d-activity-report-export-extraction
```

---

## Previous checkpoint (S1.C1) — APPROVED

```text
S1.C1 Activity Service Extraction Review
```

Verdict: APPROVED. No P0/P1 blockers. The S1.1 activity service boundary
(S1.1A–S1.1D) is accepted as a coherent activity-domain service boundary;
tenant safety and existing behavior preserved; tests sufficient to prepare S1.2.

Findings recorded (see DECISIONS_LOG D015):

```text
- P0: none
- P1: none
- P2: standardize commit/rollback ownership convention during/around S1.2
- P2: S1.2 timesheet must use a NEW file services/timesheet_service.py
- P3: export_edifico/export_edifico_preview intentionally deferred in routes
- P3: sterge (activity delete) unextracted and acceptable
```

Completed S1.1 activity service boundary:

```text
S1.1A Activity Service Skeleton + Read/Form Context Extraction
S1.1B Activity Create/Edit Save Extraction
S1.1C Activity Workflow Transition Extraction
S1.1D Activity Reports / Exports Data Assembly Extraction
```

---

## Goal of the current gate (S1.2 no-code)

Prove understanding of the safe boundary for S1.2 BEFORE any code:

1. Confirm canonical worktree state (clean, HEAD f840eb7).
2. Identify the timesheet (Pontaj) routes/logic in routes/pontaje.py that are
   candidates for extraction into a NEW services/timesheet_service.py.
3. Identify the no-touch surfaces (activity service, other domains, layout,
   imports).
4. Map the existing tenant-safe timesheet helpers already used
   (query_timesheets_for_tenant, get_timesheet_or_404,
   require_timesheet_inputs_same_tenant, etc.) so S1.2 reuses them.
5. Decide the commit/rollback convention to standardize (D015 P2).
6. Produce a non-overlap / hunk-safety plan.
7. List the files likely allowed for S1.2.
8. End by requiring Albert's explicit approval before coding.

The gate must NOT modify code, tests, services, or routes.

---

## Scope of the eventual S1.2 (for reference only — not authorized yet)

When approved, S1.2 will extract timesheet (Pontaj) domain logic from
routes/pontaje.py into a NEW file services/timesheet_service.py, per D014 + D015:

- Extract timesheet behavior only.
- New file: services/timesheet_service.py (NOT activity_service.py).
- No schema changes.
- Preserve workflows, statuses, exports, and layouts.
- MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use services/security/tenant_access.py timesheet helpers.
- No raw Pontaj/Proiect/Angajat/BIM lookups in new service code.
- Standardize the commit/rollback ownership convention (D015 P2).
- Add direct service-level tests.

---

## Do not start

Do not start implementation of:

```text
S1.2 Timesheet Service Extraction
```

Do not create services/timesheet_service.py yet.

The current authorized task is ONLY the S1.2 no-code understanding /
collision-safety gate. Implementation requires a separate explicit approval.
