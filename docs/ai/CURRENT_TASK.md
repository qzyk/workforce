# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.3 Project Service No-Code Understanding / Collision Safety Gate
```

This is a READ-ONLY gate. It produces a no-code understanding / collision-safety
report only.

IMPORTANT: S1.3 IMPLEMENTATION IS NOT AUTHORIZED.
Project Service extraction may start only after this no-code gate is reviewed and
approved by Albert.

Current canonical base commit:

```text
0a7da26 S1.2D2 timesheet import excel extraction
```

Current canonical branch:

```text
feat/s1.2d2-timesheet-import-excel-extraction
```

---

## Previous completed review (S1.C2) — APPROVED

```text
S1.C2 Timesheet Service Extraction Review — APPROVED (no P0/P1 blockers)
```

Verdict: S1.2 Timesheet Service Extraction is APPROVED (see DECISIONS_LOG D016).

S1.C2 recorded outcome:

```text
- services/timesheet_service.py is a coherent, HTTP-free Pontaj/timesheet service
- routes/pontaje.py keeps HTTP/upload/download/flash/redirect/render/jsonify/send_file
- all intended S1.2 route slices delegate correctly
- tenant safety preserved; no new raw tenant-owned queries
- only Pontaj.query.get is the isolated off-mode legacy branch of bulk approval
- monthly export data stays scoped via query_timesheets_for_tenant()
- import_excel preserves skip-per-row, partial success, single final commit
- import_excel intentionally avoids tenant_id_for_new_record_or_403() and
  require_timesheet_inputs_same_tenant()
- service-commit / route-rollback convention consistent
- read-only helpers read-only; mutating helpers commit; route rollback wrappers present
- tests sufficient
```

S1.C2 review re-ran (read-only, no code changes):

```text
py_compile OK
targeted suite (service 87 + tenant_access 6 + integration 23): 116 passed
export-layout regression: 5 passed
activity boundary: 40 passed
Flask smoke: ok 18 pontaje routes
Last full suite (at S1.2D2): 1133 passed, 39 skipped, 4 warnings
```

P3 / informational (cleanup NOT authorized): sterge + template_import route-resident
deferrals; export layout/send_file + import upload/load_workbook/flash/redirect
route-owned; get_project_employees_for_timesheet AngajatProiect.query accepted;
_detect_import_tip_zi duplicate accepted; docs/audits absent; CLAUDE.md stale.

---

## Goal of the current gate (S1.3 no-code)

Prove understanding of the Project Service boundary BEFORE any code:

```text
1. Understand current project domain logic.
2. Inspect routes/proiecte.py and related project helpers/services.
3. Understand the project tenant guard status from T1.2 / T1.12.
4. Identify safe service extraction boundaries.
5. Identify no-touch surfaces.
6. Identify collision risk with contract / commercial logic.
7. Identify whether Project Service should be split into smaller slices.
8. Produce a no-code report only.
9. Do not implement.
```

---

## Initial scope for the S1.3 gate

```text
- Project Service boundary only
- no Contract Service implementation
- no Commercial / SituatieLunara implementation
- no schema changes
- no migrations
- no templates
- no frontend rewrite
- no activity / timesheet changes
```

Follow the same constraints as the S1.x service extraction line (D014 + D015 +
D016): extract one domain's behavior only; no schema changes; preserve workflows
and statuses; MULTI_TENANT_MODE=off compatible; fail closed in strict mode; use
tenant_access.py helpers; no raw tenant-owned lookups in new service code;
service-commit / route-rollback convention; a NEW service file per domain (do not
bloat activity or timesheet services); next boundary starts with a no-code gate.

---

## No-touch boundaries for the S1.3 gate

```text
- do not modify code, tests, routes, services
- do not modify models / migrations / templates
- do not start S1.3 implementation
- do not start Project Service extraction
- do not touch activity service / routes / tests
- do not touch the approved timesheet service boundary
- do not alter completed S1.2 helpers
```

---

## Do not start

Do not start any implementation. The current authorized task is ONLY the S1.3
Project Service no-code understanding / collision-safety gate (report only). Any
follow-up implementation requires a separate explicit approval from Albert.
