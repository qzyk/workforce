# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
C1A Contract Core List Context Extraction
```

This is a narrow read-only implementation slice.

Contract Service implementation is authorized only for the contract list context
boundary. Do not perform broad Contract Service extraction.

Commercial / SituatieLunara implementation is NOT authorized.
Contract detail extraction is NOT authorized in C1A.
Create/edit/delete extraction is NOT authorized in C1A.

Do not start C1A from a docs-only coordination prompt. C1A implementation may
start only when Albert explicitly provides the C1A implementation prompt.

Current canonical base commit:

```text
2fb137f T1.5D contract render child tenant guard
```

Current canonical branch:

```text
feat/s1.4a-project-details-context-extraction
```

Previous completed gate:

```text
Contract Core Read/List/Detail Post-T1.5D Re-Gate — COMPLETED
Decision: C1A list context first
```

Latest coordination state after this docs update:

```text
T1.5C closed the responsible-user tenant/input P1.
T1.5D closed the Contract Core render-time child tenant-safety P1.
The post-T1.5D re-gate found no P0/P1 in Contract Core read/list/detail.
Contract Core service extraction may begin only with C1A list context.
Contract detail, Commercial / SituatieLunara, and broad Contract Service
extraction remain deferred.
```

---

## Previous completed gate — COMPLETED

```text
Contract Core Read/List/Detail Post-T1.5D Service Boundary Re-Gate
```

Gate verdict:

```text
P0: none
P1: none
```

The gate confirmed:

```text
- T1.5C responsible-user tenant/input blocker remains closed
- T1.5D render-time child tenant-safety blocker remains closed
- contract list/detail route-level tenant safety is sufficient for service-boundary planning
- contract list is narrow enough for the first read-only service extraction slice
- contract detail is tenant-safe but broader because it aggregates child domains
- first implementation slice should be list-only
- C1B Contract Detail Context Extraction is deferred until after C1A review
- no broad Contract Service extraction is approved
- Commercial / SituatieLunara extraction is not approved
```

Post-fix gate test baseline:

```text
py_compile passed
contract targeted tests: 50 passed
broad tenant regression: 256 passed
project regression: 60 passed
activity/timesheet regression: 150 passed
Flask smoke: ok 365
```

Remaining findings:

```text
P2:
- detail extraction should be separate from list because it aggregates multiple child domains
- add service-level tests before extracting contract list context

P3:
- delete route still uses c.acte_aditionale.count(), out of current list scope
- raw form queries remain route-overridden and out of current list/detail scope
```

---

## C1A Implementation Goal

Create or update `services/contract_service.py` with a narrow HTTP-free helper
for contract list context only.

Move only contract list data assembly into the service. Preserve the route as
the HTTP boundary.

The route must keep ownership of:

```text
- decorators
- blueprint feature gate
- request.args parsing
- render_template
- HTTP-visible behavior
```

The C1A implementation must preserve:

```text
- status filter
- project filter through get_project_or_404 or equivalent route-owned validation
- search over nr_contract / beneficiar / antreprenor
- main-contract-only behavior
- order by data_semnare desc
- stats counts
- visible project choices
- tenant-scoped addendum counts from T1.5D
- template name contracte/lista.html
- existing context keys
```

---

## Initial Allowed Files for C1A

```text
services/contract_service.py
routes/contracte.py
tests/unit/test_contract_service.py
tests/integration/test_tenant_access_contract_routes.py (targeted compatibility only, if needed)
```

---

## No-Touch Boundaries for C1A

```text
no contract detail extraction
no templates
no forms
no models
no migrations
no create/edit/delete
no term/milestone mutation routes
no PV/export/reporting
no Commercial / SituatieLunara
no Oferta / BoQ
no claims/revendicari
no Project service changes
no Project hub changes
no Gantt/BIM/Activity/Timesheet changes
no static/frontend
no route URL changes
```

---

## Explicit Deferrals

Do not start any of these without a later explicit approval:

```text
C1B Contract Core Detail Context Extraction
Contract create/edit/delete extraction
Contract term/milestone extraction
Commercial / SituatieLunara extraction
Oferta / BoQ extraction
Claims / Revendicari extraction
PV/export/reporting extraction
Gantt / BIM / Activity / Timesheet changes
schema/model/migration/template/static/frontend changes
```
