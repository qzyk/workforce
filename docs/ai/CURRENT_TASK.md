# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.1D No-Code Understanding / Collision Safety Gate
```

This is a READ-ONLY understanding and collision-safety gate for the next
extraction step (S1.1D Activity Reports/Exports Cleanup). It produces an
understanding/collision-safety report only.

IMPORTANT: S1.1D IMPLEMENTATION IS NOT YET AUTHORIZED.
S1.1D implementation may start only after this no-code safety gate is reviewed
and approved by Albert.

Current canonical base commit:

```text
6188540 S1.1C activity workflow extraction
```

Current canonical branch:

```text
feat/s1.1c-activity-workflow-extraction
```

---

## Previous step (S1.1C) — VALIDATED

```text
S1.1C Activity Workflow Transition Extraction
```

Validated by Albert based on the completion report.

S1.1C summary:

```text
- added submit_activity_for_approval() to services/activity_service.py
- added approve_activity()
- added reject_activity()
- added bulk_transition_activities()
- routes/activitati.py keeps trimite/aproba/respinge/aprobare_masa as thin
  HTTP wrappers
- route decorators, flash messages, redirects, status transitions, db commit
  behavior, and tenant behavior were preserved
- off-mode legacy bulk behavior was preserved
- no schema changes
- no migrations
- no create/edit save changes
- no read/form context changes
- no report/export extraction
- no Pontaj/BIM/Contract/Gantt/HR/Fleet changes
- no S1.1D/S1.2 started
```

Tests reported:

```text
32 activity service tests passed
74 targeted activity + tenant tests passed
246 tenant tests passed
50 regression/smoke tests passed
app import and 25 activitati routes OK
```

---

## Goal of the current gate (S1.1D no-code)

Prove understanding of the safe boundary for S1.1D BEFORE any code:

1. Confirm canonical worktree state (clean, HEAD 6188540).
2. Identify exactly which report/export read-side logic could move to
   activity_service (data gathering for `raport_saptamanal`, `raport_lunar`,
   `raport_anual`, `raport_proiect`, `export_edifico`, `export_edifico_preview`,
   plus the API/calendar read endpoints if relevant).
3. Draw a hard line: file/format generation (openpyxl/Excel/PDF layout) and the
   HTTP response stay in the route; only tenant-safe data assembly is a candidate.
4. Identify the no-touch functions (save, workflow, other domains).
5. Produce a non-overlap / hunk-safety plan.
6. List the files likely allowed for S1.1D.
7. End by requiring Albert's explicit approval before coding.

The gate must NOT modify code, tests, services, or routes.

---

## Scope of the eventual S1.1D (for reference only — not authorized yet)

When approved, S1.1D will be a cleanup pass extracting only the tenant-safe
report/export DATA-ASSEMBLY logic into `services/activity_service.py`, per D014,
while leaving Excel/PDF generation and HTTP responses in the route. Export file
layouts and formats must not change.

- Extract activity behavior only.
- No schema changes.
- Preserve export layouts/formats and file names exactly.
- MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use tenant_access.py helpers.
- No raw RaportActivitate/Pontaj/Proiect/Angajat/BIM lookups in new service code.
- Add direct service-level tests.

---

## Do not start

Do not start implementation of:

```text
S1.1D Activity Reports/Exports Cleanup
S1.2 Timesheet Service Extraction
```

The current authorized task is ONLY the S1.1D no-code understanding /
collision-safety gate. Implementation requires a separate explicit approval.
