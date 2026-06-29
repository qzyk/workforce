# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.1B No-Code Understanding / Collision Safety Gate
```

This is a READ-ONLY understanding and collision-safety gate for the next
extraction step (S1.1B Activity Create/Edit Extraction). It produces an
understanding/collision-safety report only.

IMPORTANT: S1.1B IMPLEMENTATION IS NOT YET AUTHORIZED.
S1.1B implementation may start only after this no-code safety gate is reviewed
and approved by Albert.

Current canonical base commit:

```text
00b4fd1 S1.1A activity service read context extraction
```

Current canonical branch:

```text
feat/s1.1a-activity-service-read-context
```

---

## Previous step (S1.1A) — VALIDATED

```text
S1.1A Activity Service Skeleton + Read/Form Context Extraction
```

Validated by Albert based on the completion report.

S1.1A summary:

```text
- created services/activity_service.py
- extracted low-risk activity panel/read/form-context logic
- routes/activitati.py now delegates read/form context to activity_service
- no schema changes
- no migrations
- no workflow changes
- no export changes
- no approval changes
- no S1.1B/S1.1C/S1.1D started
```

Tests reported:

```text
7 service tests passed
49 targeted tests passed
246 tenant tests passed
39 regression tests passed
11 smoke tests passed
```

---

## Goal of the current gate (S1.1B no-code)

Prove understanding of the safe boundary for S1.1B BEFORE any code:

1. Confirm canonical worktree state (clean, HEAD 00b4fd1).
2. Identify exactly which create/edit save logic would move to activity_service.
3. Identify the no-touch functions (workflow transitions, exports).
4. Produce a non-overlap / hunk-safety plan.
5. List the files likely allowed for S1.1B.
6. End by requiring Albert's explicit approval before coding.

The gate must NOT modify code, tests, services, or routes.

---

## Scope of the eventual S1.1B (for reference only — not authorized yet)

When approved, S1.1B will extract activity create/edit save behavior
(`_salveaza_activitate`) into `services/activity_service.py`, per D014:

- Extract activity behavior only.
- No schema changes.
- Preserve workflows and statuses.
- MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use tenant_access.py helpers
  (require_activity_inputs_same_tenant, require_activity_bim_context_same_tenant,
   tenant_id_for_new_record_or_403).
- No raw RaportActivitate/Pontaj/Proiect/Angajat/BIM lookups.
- Add direct service-level tests.

---

## Do not start

Do not start implementation of:

```text
S1.1B Activity Create/Edit Extraction
S1.1C Activity Workflow Transitions
S1.1D Activity Reports/Exports Cleanup
S1.2 Timesheet Service Extraction
```

The current authorized task is ONLY the S1.1B no-code understanding /
collision-safety gate. Implementation requires a separate explicit approval.
