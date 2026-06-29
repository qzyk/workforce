# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.1C No-Code Understanding / Collision Safety Gate
```

This is a READ-ONLY understanding and collision-safety gate for the next
extraction step (S1.1C Activity Workflow Transitions). It produces an
understanding/collision-safety report only.

IMPORTANT: S1.1C IMPLEMENTATION IS NOT YET AUTHORIZED.
S1.1C implementation may start only after this no-code safety gate is reviewed
and approved by Albert.

Current canonical base commit:

```text
bc98a29 S1.1B activity save extraction
```

Current canonical branch:

```text
feat/s1.1b-activity-save-extraction
```

---

## Previous step (S1.1B) — VALIDATED

```text
S1.1B Activity Create/Edit Save Extraction
```

Validated by Albert based on the completion report.

S1.1B summary:

```text
- added save_activity_from_form_data() to services/activity_service.py
- added ActivityValidationError
- moved create/edit save parsing, validation, field assignment, JSON
  serialization, BIM context validation, inline save status logic,
  calculeaza_perioada(), and db commit into activity_service
- routes/activitati.py keeps _salveaza_activitate as a thin HTTP wrapper
- route behavior, flash messages, redirects, jsonify shape, approval
  workflow, and exports remain unchanged
- no schema changes
- no migrations
- no workflow route extraction
- no export/report extraction
- no S1.1C/S1.1D/S1.2 started
```

Tests reported:

```text
19 activity service tests passed
61 targeted activity + tenant tests passed
246 tenant tests passed
50 regression/smoke tests passed
app import and 25 activitati routes OK
```

---

## Goal of the current gate (S1.1C no-code)

Prove understanding of the safe boundary for S1.1C BEFORE any code:

1. Confirm canonical worktree state (clean, HEAD bc98a29).
2. Identify exactly which workflow-transition logic would move to activity_service
   (the routes `trimite`, `aproba`, `respinge`, `aprobare_masa`, and the relevant
   bits of `sterge` if applicable).
3. Identify the no-touch functions (save, reports, exports, other domains).
4. Analyze the status/approval state machine that must be preserved exactly.
5. Produce a non-overlap / hunk-safety plan.
6. List the files likely allowed for S1.1C.
7. End by requiring Albert's explicit approval before coding.

The gate must NOT modify code, tests, services, or routes.

---

## Scope of the eventual S1.1C (for reference only — not authorized yet)

When approved, S1.1C will extract the activity workflow-transition logic
(status changes: draft -> trimis -> aprobat/respins, plus batch approval) into
`services/activity_service.py`, per D014:

- Extract activity behavior only.
- No schema changes.
- Preserve workflow statuses and transition rules exactly.
- MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use tenant_access.py helpers (get_activity_or_404, get_tenant_mode, etc.).
- No raw RaportActivitate/Pontaj/Proiect/Angajat/BIM lookups.
- Add direct service-level tests.

---

## Do not start

Do not start implementation of:

```text
S1.1C Activity Workflow Transitions
S1.1D Activity Reports/Exports Cleanup
S1.2 Timesheet Service Extraction
```

The current authorized task is ONLY the S1.1C no-code understanding /
collision-safety gate. Implementation requires a separate explicit approval.
