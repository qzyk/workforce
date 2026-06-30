# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
Contract Core Read/List/Detail Service No-Code Gate
```

This is a read-only no-code understanding / collision-safety gate. It is NOT
Contract Service implementation and it is NOT Commercial / SituatieLunara
Service implementation.

IMPORTANT: no `services/contract_service.py` may be created until this gate is
reviewed and approved by Albert. No Contract Core implementation is authorized
yet.

Current canonical base commit:

```text
b519d51 T1.5C contract term responsible tenant guard
```

Latest coordination state after this docs update:

```text
T1.5C Review — APPROVED.
The Contract / Commercial P1 tenant/input blocker is closed.
Next authorized task: Contract Core Read/List/Detail Service No-Code Gate.
```

Current canonical branch:

```text
feat/s1.4a-project-details-context-extraction
```

---

## Previous completed review — APPROVED

```text
T1.5C Review — Contract Form/Input Tenant Guard Hardening Review
```

Verdict:

```text
APPROVED
P0: none
P1: none
```

T1.5C fixed the original Contract / Commercial P1 blocker:

```text
- TermenContractForm.responsabil_id no longer uses raw all-active Utilizator.query.
- responsible-user dropdown choices are tenant-scoped.
- inactive users remain excluded.
- the empty/no responsible option is preserved.
- termen_nou validates submitted responsabil_id before save.
- termen_editeaza validates submitted responsabil_id before save.
- foreign responsible users cannot be persisted.
- responsabil_id=0 still maps to None.
- valid same-tenant responsible assignment still works.
- strict mode excludes foreign users and rejects foreign POST.
- off mode preserves legacy active-user visibility.
```

T1.5C implementation commit:

```text
b519d51 T1.5C contract term responsible tenant guard
```

Files changed by T1.5C implementation:

```text
forms/contract_forms.py
routes/contracte.py
tests/integration/test_tenant_access_contract_routes.py
```

T1.5C review validation:

```text
py_compile forms/contract_forms.py routes/contracte.py
tests/integration/test_tenant_access_contract_routes.py: OK
contract route tests: 22 passed
contract baseline: 45 passed
broad tenant regression: 251 passed
project regression: 60 passed
activity/timesheet regression: 150 passed
Flask smoke: ok 365
full suite: 1183 passed, 39 skipped, 4 warnings
```

No schema, model, template, service extraction, Project service, Project hub, or
Contract / Commercial extraction changes occurred in T1.5C.

---

## Current gate goal

The Contract Core Read/List/Detail Service No-Code Gate must inspect
`routes/contracte.py` contract core read surfaces only.

Focus only on:

```text
- lista
- detalii
- read/list/detail context helpers
```

The gate must identify exact route-owned HTTP behavior:

```text
- request args
- WTForms if relevant
- flash/redirect if any
- render_template
- url_for
- pagination/search/filter/sort behavior
```

The gate must identify exact model/query behavior:

```text
- Contract
- Proiect
- child context shown in detalii, if any
- addenda / terms / PVs if displayed in detalii
```

The gate must verify tenant helper usage:

```text
- query_contracts_for_tenant
- get_contract_or_404
- related helper calls
```

The gate must decide whether a later implementation slice should be:

```text
- Contract core read/list context extraction
- Contract detail context extraction
- split A/B
- or no implementation yet
```

The output must be a no-code report only.

---

## No-touch boundaries for the current gate

```text
- no implementation
- no services/contract_service.py
- no Contract create/edit/delete extraction
- no Contract term/milestone mutation or extraction
- no Commercial / SituatieLunara extraction
- no Oferta / BoQ extraction
- no Claims / Revendicari extraction
- no PV/export/reporting extraction
- no Project service changes
- no Project hub changes
- no Gantt/BIM/Activity/Timesheet changes
- no models
- no migrations
- no templates/frontend/static
- no route URL changes
```

---

## Do not start

Do not start Contract Service implementation. Do not start Commercial /
SituatieLunara implementation. Do not create `services/contract_service.py`.
Do not modify commercial/reporting services. The current authorized task is only
the Contract Core Read/List/Detail no-code gate.
