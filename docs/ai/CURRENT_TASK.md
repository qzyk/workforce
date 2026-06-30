# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
Contract Core Read/List/Detail Post-T1.5D Service Boundary Re-Gate
```

This is a read-only no-code gate.

Contract Service implementation is NOT authorized.
Commercial / SituatieLunara implementation is NOT authorized.

No `services/contract_service.py` may be created until this post-fix gate is
reviewed and approved by Albert.

Current canonical base commit:

```text
2fb137f T1.5D contract render child tenant guard
```

Current canonical branch:

```text
feat/s1.4a-project-details-context-extraction
```

Latest completed review:

```text
T1.5D Review — Contract List/Detail Render-Time Child Tenant Guard APPROVED
```

Latest coordination state after this docs update:

```text
T1.5D closed the Contract Core render-time child tenant-safety P1 blockers.
Contract Core service extraction is still not directly authorized.
The next step is a post-fix no-code service boundary re-gate.
```

---

## Previous completed review — APPROVED

```text
T1.5D Review — Contract List/Detail Render-Time Child Tenant Guard Review
```

Review verdict:

```text
APPROVED
P0: none
P1: none
```

The review confirmed:

```text
- original render-time child tenant-safety P1 blockers are fixed
- contract list no longer uses template-level c.acte_aditionale.count()
- contract detail no longer uses direct template lazy access for:
  - contract.programe_referinta
  - contract.oferte
  - o.pozitii.count()
- contract list/detail consume pre-scoped route context for flagged child data
- strict mode hides/counts only same-tenant children
- optional mode with tenant hides foreign child rows
- off mode preserves legacy unfiltered behavior through existing tenant helpers
- list/detail remain read-only
- no service extraction was started
- no services/contract_service.py was created
- no model/migration/form/static/frontend changes occurred
- no Project service / Project hub changes occurred
- no Commercial / SituatieLunara changes occurred
```

Review / test baseline:

```text
py_compile routes/contracte.py tests/integration/test_tenant_access_contract_routes.py: OK
contract route tests: 27 passed
contract baseline: 50 passed
broad tenant regression: 256 passed
project regression: 60 passed
activity/timesheet regression: 150 passed
Flask smoke: ok 365
full suite: 1188 passed, 39 skipped, 4 warnings
```

Remaining review note:

```text
P3 only: existing c.acte_aditionale.count() in routes/contracte.py::sterge
remains outside T1.5D scope and is not a blocker for list/detail render-path
safety.
```

---

## Gate Goal

The Contract Core Post-T1.5D Re-Gate must:

```text
- confirm the original list/detail P1 blockers are closed
- re-inspect contract lista and detalii after T1.5D
- verify render-time child tenant leaks are gone
- verify list/detail are now suitable candidates for HTTP-free read context extraction
- decide the first safe implementation slice:
  - C1A Contract Core List Context Extraction
  - C1B Contract Core Detail Context Extraction
  - C1A/C1B split sequence
  - or more hardening before implementation
- define exact allowed files for the first implementation slice
- define exact no-touch surfaces
- produce a no-code report only
```

---

## Initial Scope for Next Gate

```text
- Contract core read/list/detail only
- no implementation
- no create/edit/delete
- no term/milestone mutation
- no Commercial / SituatieLunara
- no Oferta / BoQ
- no Claims / Revendicari
- no PV/export/reporting
- no Project service changes
- no Project hub changes
- no Gantt/BIM/Activity/Timesheet changes
- no schema changes
- no migrations
- no templates/frontend changes unless the gate only reads them
- no route URL changes
```

---

## Explicit Deferrals

Do not start any of these without a later explicit approval:

```text
Contract Service implementation
Contract create/edit/delete extraction
Contract term/milestone extraction
Commercial / SituatieLunara extraction
Oferta / BoQ extraction
Claims / Revendicari extraction
PV/export/reporting extraction
Gantt / BIM / Activity / Timesheet changes
```
