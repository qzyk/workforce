# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
T1.5D Contract List/Detail Render-Time Child Tenant Guard
```

This is a narrow tenant-safety hardening task.

It is NOT Contract Service extraction. It is NOT Commercial / SituatieLunara
Service extraction.

No `services/contract_service.py` may be created. No Contract Core service
extraction is authorized until the render-time child tenant-safety P1 issue is
fixed and reviewed.

Current canonical base commit:

```text
b519d51 T1.5C contract term responsible tenant guard
```

Latest coordination state after this docs update:

```text
Contract Core Read/List/Detail Gate completed.
Contract Core service extraction is NOT approved due to P1 render-time child
tenant-safety blockers.
The latest coordination commit is this docs-only update:
Update AI coordination state after contract core gate
```

Current canonical branch:

```text
feat/s1.4a-project-details-context-extraction
```

---

## Previous completed gate — NOT APPROVED FOR EXTRACTION

```text
Contract Core Read/List/Detail Service No-Code Gate
```

Gate verdict:

```text
P0: none
P1: present
Contract Core Read/List/Detail Service Extraction is NOT approved yet.
Contract Service implementation is NOT authorized.
```

The gate confirmed:

```text
- contract list route uses query_contracts_for_tenant()
- contract list filters status, project, and search
- contract list renders contracte/lista.html
- contract detail route uses get_contract_or_404()
- contract detail renders contracte/detalii.html
- list/detail routes are read-only and route logic is broadly tenant-safe
- templates and relationships still perform render-time lazy child queries
  outside explicit tenant helper control
```

P1 blockers:

```text
- templates/contracte/detalii.html performs unscoped render-time lazy queries:
  - contract.programe_referinta
  - contract.oferte
  - o.pozitii.count()
- routes/contracte.py::detalii and templates/contracte/lista.html use
  acte_aditionale relationship queries/counts without explicit tenant scoping.
```

Risk:

```text
These child models have tenant ownership and can leak under historical/corrupted
cross-tenant links.
```

Gate test baseline:

```text
py_compile routes/contracte.py forms/contract_forms.py contract tests: OK
contract targeted suite: 45 passed
project regression: 60 passed
activity/timesheet regression: 150 passed
Flask smoke: ok 365
```

---

## T1.5D goal

T1.5D must:

```text
- remove or neutralize render-time lazy relationship tenant leaks in contract
  list/detail
- tenant-scope addenda counts/collections
- tenant-scope detail child collections displayed in contracte/detalii.html:
  - ProgramReferinta
  - OfertaContract
  - PozitieBoQ counts
  - acte_aditionale
- preserve current visible behavior
- preserve template names and route URLs
- avoid broad redesign
- add targeted tests for cross-tenant child rows attached to a valid
  tenant-owned parent
- not create services/contract_service.py
- not perform service extraction
- not change schema/models
- not change commercial workflows
```

Initial allowed implementation files should likely be:

```text
routes/contracte.py
templates/contracte/lista.html
templates/contracte/detalii.html
tests/integration/test_tenant_access_contract_routes.py
```

The implementation prompt may narrow this further after reviewing the current
code.

---

## No-touch boundaries for T1.5D

```text
- no services/contract_service.py
- no Contract Core service extraction
- no Commercial / SituatieLunara service changes
- no Oferta / BoQ workflow changes beyond safe read context/count passing if
  strictly necessary
- no PV/export/reporting workflow changes
- no Project service changes
- no Project hub changes
- no Gantt/BIM/Activity/Timesheet changes
- no forms unless unavoidable
- no models
- no migrations
- no route URL changes
- no broad template redesign
- no static/frontend changes
```

---

## After T1.5D

After T1.5D is implemented and reviewed, Contract Core read/list/detail service
planning may resume through a new approved prompt.

Potential later options:

```text
Contract Core List Context Extraction
Contract Core Detail Context Extraction
Contract Core C1A/C1B split
Commercial / SituatieLunara sub-gate
Oferta / BoQ sub-gate
PV/export/reporting sub-gate
```

Do not start any of those now.
