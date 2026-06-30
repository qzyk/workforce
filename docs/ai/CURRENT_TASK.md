# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.3B Project Create/Edit/Status No-Code Understanding / Collision Safety Gate
```

This is a READ-ONLY gate. It produces a no-code understanding / collision-safety
report only.

IMPORTANT: S1.3B IMPLEMENTATION IS NOT AUTHORIZED.
Project create/edit/status extraction may start only after this no-code gate is
reviewed and approved by Albert. Broad Project Service extraction is NOT authorized.

Current canonical base commit:

```text
ed2c780 S1.3A project read list service extraction
```

Current canonical branch:

```text
feat/s1.3a-project-service-read-list-extraction
```

---

## Previous completed step (S1.3A) — VALIDATED

```text
S1.3A Project Service Read/List + Financial Data Assembly Extraction
```

Verdict: COMPLETE. A new HTTP-free, read-only `services/project_service.py` was
created; the `lista` read/list context and the four read-only financial helpers
were extracted, without touching create/edit/status, cross-domain routes, or any
other domain.

S1.3A recorded results:

```text
- services/project_service.py created (NEW; HTTP-free; read-only)
- get_project_managers(), get_project_list_context() (list/filter/sort/pagination/
  stats/managers context for lista)
- get_project_total_hours(), calculate_project_labor_cost(),
  get_project_weekly_hours(), get_project_monthly_costs() (financial data)
- routes/proiecte.py lista delegates read/list context to the service
- route helper wrappers kept (thin delegations) for detalii:
  _get_total_ore, _calculeaza_cost_manopera, _get_ore_saptamanale, _get_cost_lunar
- route still owns request.args, render_template, decorators, HTTP boundary
- service is read-only: no db.session.add/delete/commit/rollback; no rollback wrappers
- tenant safety preserved: query_for_tenant(Proiect), query_users_for_tenant,
  query_timesheets_for_tenant, query_project_assignments_for_tenant (thread tenant_id)
- foreign project -> 0 (fail-closed); strict/optional/off preserved
- no new raw Proiect/Pontaj/Angajat/RaportActivitate.query in project_service.py
- pre-existing adauga auto-code Proiect.query global count left untouched (S1.3B scope)
- adauga / editeaza / schimba_status / hub / detalii / nested / reports untouched
- Activity / Timesheet / Contract / Gantt / Commercial untouched
- models / migrations / templates / static / frontend untouched
```

S1.3A validation:

```text
project service unit tests (test_project_service.py): 19 passed
project targeted suite (service + route/nested/hub/locations): 54 passed
regression safety (activity + timesheet + timesheet routes): 150 passed
Flask app smoke (proiecte routes): ok 27
full suite (tests/unit + tests/integration): 1152 passed, 39 skipped, 4 warnings
git diff --check clean
```

Files changed in ed2c780:

```text
services/project_service.py (new)
routes/proiecte.py
tests/unit/test_project_service.py (new)
```

---

## Goal of the current gate (S1.3B no-code)

Prove understanding of the Project create/edit/status save boundary BEFORE any code:

```text
1. Understand current adauga (create) behavior.
2. Understand current editeaza (update) behavior.
3. Understand current schimba_status (status, JSON) behavior.
4. Understand manager validation (query_users_for_tenant first_or_404).
5. Understand tenant_id assignment for a new Project (tenant_id_for_new_record_or_403).
6. Understand auto cod_proiect generation and the existing global Proiect.query count.
7. Understand field mapping / defaults.
8. Understand locatie composition (judet/localitate) and the GET split-back behavior.
9. Understand status transition behavior (finalizat -> data_sfarsit_real).
10. Understand current in-route commit behavior and the lack of rollback wrappers.
11. Propose a safe service extraction boundary (service-commit / route-rollback).
12. Preserve route-owned ProiectForm / validate_on_submit / flash / redirect / jsonify.
13. Produce a no-code report only. Do not implement.
```

---

## Initial scope for the S1.3B gate

```text
- Project create/edit/status only (adauga, editeaza, schimba_status)
- no list/read extraction changes
- no financial helper changes
- no detalii extraction
- no hub extraction
- no nested resource routes
- no Contract / Commercial / Gantt / Activity / Timesheet changes
- no schema changes
- no migrations
- no templates / static / frontend
```

Follow the S1.x service-extraction constraints (D014 + D015 + D016): extract one
domain's behavior only; no schema changes; preserve workflows/statuses;
MULTI_TENANT_MODE=off compatible; fail closed in strict mode; use tenant_access.py
helpers; no raw tenant-owned lookups in new service code (the pre-existing
auto-code count stays in the route); reuse the existing services/project_service.py
(do not create another project file); apply service-commit / route-rollback for the
mutating slice.

---

## No-touch boundaries for the S1.3B gate

```text
- do not modify code, tests, routes, services
- do not modify models / migrations / templates / static / frontend
- do not start S1.3B implementation
- do not start broad Project Service extraction
- do not touch the approved S1.3A read/list + financial boundary
- do not touch Activity / Timesheet / Contract / Gantt / Commercial domains
```

---

## Do not start

Do not start any implementation. The current authorized task is ONLY the S1.3B
Project create/edit/status no-code understanding / collision-safety gate (report
only). Any follow-up implementation requires a separate explicit approval from Albert.
