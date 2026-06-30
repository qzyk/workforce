# PROJECT_STATE.md — Canonical Project State for AI Agents

Last updated after:

```text
T1.5D Review — Contract List/Detail Render-Time Child Tenant Guard APPROVED
```

Canonical repository:

```text
qzyk/workforce
```

Canonical worktree:

```text
/Users/albertciolacu/workforce-t1.5-contract
```

Do not work in:

```text
/Users/albertciolacu/workforce
```

External Claude worktrees:

```text
/Users/albertciolacu/workforce/.claude/worktrees/
```

Status of external Claude worktrees:

```text
External non-authoritative experimental worktrees.
Excluded from canonical reviews and implementation tasks.
Do not merge, clean, delete, or copy from them.
```

---

## Current canonical branch

```text
feat/s1.4a-project-details-context-extraction
```

## Current canonical tenant-fix code boundary

```text
2fb137f T1.5D contract render child tenant guard
```

## Previous tenant-fix boundary

```text
b519d51 T1.5C contract term responsible tenant guard
```

## Approved Project-owned code boundary

```text
4c15b01 S1.4A project details context extraction
```

Latest coordination state:

```text
T1.5D closed the Contract Core render-time child tenant-safety P1 blockers.
Contract Core service extraction is still not directly authorized.
The next step is a post-fix no-code service boundary re-gate.
```

## Current test / gate baseline

T1.5D review approved the render-time child tenant-safety fix. The Project-owned
service boundary remains S1.4A.

```text
T1.5D review py_compile routes/contracte.py
tests/integration/test_tenant_access_contract_routes.py: OK
T1.5D contract route tests: 27 passed
T1.5D contract baseline: 50 passed
T1.5D broad tenant regression: 256 passed
T1.5D project regression: 60 passed
T1.5D activity/timesheet regression: 150 passed
T1.5D Flask smoke: ok 365
T1.5D full suite: 1188 passed, 39 skipped, 4 warnings
T1.5C review py_compile forms/contract_forms.py routes/contracte.py
tests/integration/test_tenant_access_contract_routes.py: OK
T1.5C contract route tests: 22 passed
T1.5C contract baseline: 45 passed
T1.5C broad tenant regression: 251 passed
T1.5C project regression: 60 passed
T1.5C activity/timesheet regression: 150 passed
T1.5C Flask smoke: ok 365
T1.5C full suite: 1183 passed, 39 skipped, 4 warnings
Contract Core gate py_compile: OK
Contract Core gate contract targeted suite: 45 passed
Contract Core gate project regression: 60 passed
Contract Core gate activity/timesheet regression: 150 passed
Contract Core gate Flask smoke: ok 365
Contract / Commercial gate py_compile routes/contracte.py services/situatii.py
services/evm.py services/rapoarte_lucrari.py: OK
Contract / Commercial suite: 139 passed
Project regression: 67 passed
Activity/Timesheet regression: 150 passed
Flask smoke equivalent: ok 365 routes
S1.5 gate py_compile routes/proiecte.py services/project_service.py: OK
S1.5 gate project targeted suite: 80 passed
S1.5 gate cross-domain regression suite: 150 passed
S1.5 gate Flask project route smoke: ok 27 proiecte.* routes
project service unit tests (tests/unit/test_project_service.py): 45 passed (34 prior + 11 new S1.4A)
project targeted suite (service + project route/nested/hub/locations): 80 passed
cross-domain regression (timesheet routes + activity + timesheet service): 150 passed
Flask app smoke (proiecte routes): ok 27
full suite (tests/unit + tests/integration): 1178 passed, 39 skipped, 4 warnings
git diff --check clean
```

---

## Completed tenant guard stack

```text
T1.1  tenant access foundation
T1.2  project tenant guard
T1.3  activity tenant guard
T1.4  timesheet tenant guard
T1.5  contract tenant guard
T1.6  document tenant guard
T1.7  BIM tenant guard
T1.8  Gantt tenant guard
T1.9  dashboard reporting tenant guard
T1.10 HR fleet tenant guard
T1.11 notifications admin tenant guard
T1.12 project nested tenant guard
T1.13 locations audit api tokens tenant guard
T1.14 activity BIM context tenant guard
```

T1.C14 APPROVED. Tenant guard phase complete.

---

## Completed service extraction steps

```text
S1.1A Activity Service Skeleton + Read/Form Context Extraction
S1.1B Activity Create/Edit Save Extraction
S1.1C Activity Workflow Transition Extraction
S1.1D Activity Reports / Exports Data Assembly Extraction
S1.2A Timesheet Service Skeleton + Read/List Context Extraction
S1.2B1 Timesheet Single Create/Edit Save Extraction
S1.2B2 Timesheet Bulk Create Save Extraction
S1.2C1 Timesheet Single Workflow Extraction
S1.2C2 Timesheet Bulk Workflow Extraction
S1.2D1 Timesheet Monthly Export Data Assembly Extraction
S1.2D2 Timesheet Import Excel Parsing/Create Extraction
S1.C2 Timesheet Service Extraction Review — APPROVED
S1.3 Project Service No-Code Understanding / Collision Safety Gate — APPROVED
S1.3A Project Service Read/List + Financial Data Assembly Extraction
S1.3B Project Create/Edit/Status Save Extraction
S1.C3 Project Service Extraction Review — APPROVED
S1.4 Project Details / Cross-Domain Context No-Code Gate — APPROVED
S1.4A Project Details Context Extraction
S1.C4 Project Details Context Extraction Review — APPROVED
S1.5 Project Hub / Cross-Domain Aggregator No-Code Gate — COMPLETED / HUB ROUTE-RESIDENT
Contract / Commercial Service No-Code Gate — COMPLETED / NOT APPROVED FOR EXTRACTION DUE TO P1
T1.5C Contract Form/Input Tenant Guard Hardening
T1.5C Review — Contract Form/Input Tenant Guard Hardening APPROVED
Contract Core Read/List/Detail Service No-Code Gate — COMPLETED / NOT APPROVED FOR EXTRACTION DUE TO P1
T1.5D Contract List/Detail Render-Time Child Tenant Guard
T1.5D Review — Contract List/Detail Render-Time Child Tenant Guard APPROVED
```

Latest gate checkpoint:

```text
T1.5D Review — Contract List/Detail Render-Time Child Tenant Guard APPROVED
```

T1.5D approved summary:

```text
- fixed contract list render-time addendum count lazy tenant risk
- fixed contract detail render-time child lazy tenant risks for:
  - addenda
  - ProgramReferinta
  - OfertaContract
  - PozitieBoQ counts
- templates now consume pre-scoped route context for flagged child data
- strict mode child hiding/counting verified
- optional mode with tenant child hiding verified
- off mode legacy visibility verified
- no service extraction
- no schema/model/form/static/frontend changes
- no Project service / Project hub changes
- no Commercial / SituatieLunara changes
```

Contract Core Read/List/Detail gate summary:

```text
- contract list route uses query_contracts_for_tenant()
- contract list filters status, project, and search
- contract list renders contracte/lista.html
- contract detail route uses get_contract_or_404()
- contract detail renders contracte/detalii.html
- list/detail routes are read-only and route logic is broadly tenant-safe
- however, templates and relationships perform render-time lazy child queries
  outside explicit tenant helper control
- service extraction must wait until render-time child queries are tenant-scoped
```

Contract Core Read/List/Detail P1 blockers:

```text
- templates/contracte/detalii.html:
  - contract.programe_referinta
  - contract.oferte
  - o.pozitii.count()
- routes/contracte.py::detalii and templates/contracte/lista.html:
  - acte_aditionale relationship queries/counts
- risk:
  - historical/corrupted cross-tenant child rows could be shown through
    relationship traversal
```

Contract Core gate decision:

```text
- Contract Core read/list/detail extraction is blocked by T1.5D render-time
  child tenant guard.
- Broad Contract / Commercial extraction is still not authorized.
- No services/contract_service.py may be created yet.
- Commercial / SituatieLunara extraction is still not authorized.
```

Contract / Commercial gate summary:

```text
- routes/contracte.py has broad route-level tenant safety through T1.5 helpers.
- no broad raw-query direct-access pattern was found in routes/contracte.py.
- commercial/reporting services exist but are not approved tenant-safe service
  boundaries:
  - services/situatii.py
  - services/centralizator.py
  - services/rapoarte_lucrari.py
  - services/evm.py
  - services/deviz_pricing.py
  - services/conflict_revendicare.py
  - services/pv_generator.py
- Contract core, Commercial/Situatie, Oferta/BoQ, Claims, PV/export/reporting
  must remain deferred.
- broad Contract / Commercial extraction is not authorized.
```

Original P1 blocker (closed by T1.5C / D021):

```text
- TermenContractForm.responsabil_id dropdown uses raw Utilizator.query across
  all active users.
- termen_nou / termen_editeaza save responsabil_id without same-tenant validation.
- This can leak users and allow cross-tenant responsible assignment.
- Fix required before any Contract / Commercial service extraction.
```

T1.5C approved summary:

```text
- b519d51 fixed TermenContractForm.responsabil_id dropdown tenant leakage.
- termen_nou validates submitted responsabil_id before save.
- termen_editeaza validates submitted responsabil_id before save.
- foreign responsible-user assignment is blocked.
- strict mode tenant safety verified.
- off mode legacy active-user visibility verified.
- valid same-tenant responsible assignment verified.
- responsabil_id=0 / no-responsible value preserved.
- inactive responsible users remain excluded.
- no schema/model/template/service extraction changes.
- no Project service / Project hub changes.
- no Contract / Commercial service extraction started.
```

S1.2D2 summary:

```text
- import_timesheets_from_rows() added to services/timesheet_service.py
- _detect_import_tip_zi() added to services/timesheet_service.py
- import_excel delegates row-processing/create behavior to the timesheet service
- route still owns request.files, .xlsx extension validation, load_workbook,
  wb.active worksheet selection, flash, redirect, and HTTP behavior
- expected columns preserved (CNP, cod_proiect, data, ora_start, ora_sfarsit,
  tip_zi, observatii)
- string coercion behavior preserved
- empty rows skipped silently (not counted as errors)
- bad rows counted as errors; missing/foreign employee/project rows skipped
- foreign employee/project skipped via tenant-safe query_for_tenant() (NEVER abort)
- duplicate rows skipped via query_timesheets_for_tenant()
- date parsing preserved (dd.mm.yyyy and yyyy-mm-dd)
- imported rows preserve status='draft'; approval/workflow fields untouched
- partial-success preserved: good rows created, bad/duplicate skipped,
  ONE final commit after the row loop
- NO tenant_id_for_new_record_or_403() introduced in import path
- NO require_timesheet_inputs_same_tenant() introduced in import path
  (those would convert per-row skip into abort(404))
- no raw Pontaj/Angajat/Proiect/RaportActivitate.query introduced in service
- SarbatoareLegala.query allowed only as global catalog for tip_zi detection
- route rollback wrapper added around the service call without changing
  per-row skip behavior
- query_timesheets_for_tenant and Angajat removed from routes/pontaje.py imports
  (now resolved inside the service)
- export_lunar untouched
- build_monthly_timesheet_export_data() untouched
- template_import untouched
- save/create/edit untouched
- single/bulk workflow untouched
- read/list/context untouched
- sterge untouched
- services/activity_service.py untouched
- routes/activitati.py untouched
- models.py untouched
- migrations untouched
- templates untouched
```

Files changed in 0a7da26:

```text
routes/pontaje.py
services/timesheet_service.py
tests/unit/test_timesheet_service.py
```

Test-cleanup robustness note (S1.2D2):

```text
- tests/unit/test_timesheet_service.py fixture _curata was hardened to also delete
  Pontaj rows attached to S12A employees/projects, not only rows with
  observatii like 'TEST_S12A%'.
- Reason: import-created Pontaj rows may have arbitrary observatii (empty string,
  'concediu', etc.), so the previous cleanup filter could leave orphan Pontaj rows
  before the test employees/projects were deleted (FK NOT NULL violation at teardown).
- This is a test-cleanup robustness change only; behavior-preserving for existing
  tests and confirmed by the full suite (1133 passed).
```

S1.3A summary:

```text
- services/project_service.py created (NEW project-domain service; HTTP-free, read-only)
- get_project_managers(), get_project_list_context() added (list/filter/sort/
  pagination/stats/managers context for the lista route)
- get_project_total_hours(), calculate_project_labor_cost(),
  get_project_weekly_hours(), get_project_monthly_costs() added (financial data)
- routes/proiecte.py lista delegates read/list context to the project service
- route helper wrappers preserved (thin delegations, old names kept for detalii):
  _get_total_ore, _calculeaza_cost_manopera, _get_ore_saptamanale, _get_cost_lunar
- route still owns request.args, render_template, decorators, HTTP boundary
- service is HTTP-free and read-only: no db.session.add/delete/commit/rollback
- no rollback wrappers added (S1.3A is read-only)
- tenant safety preserved: list/stats via query_for_tenant(Proiect); managers via
  query_users_for_tenant; financial via query_timesheets_for_tenant +
  query_project_assignments_for_tenant (all thread tenant_id)
- foreign project -> 0 hours (fail-closed); strict/optional/off preserved
- no new raw Proiect/Pontaj/Angajat/RaportActivitate.query in project_service.py
- pre-existing adauga auto-code Proiect.query global count left untouched (S1.3B scope)
- adauga / editeaza / schimba_status untouched (S1.3B)
- detalii untouched except continued use of the helper wrappers
- hub / evm / utilaje / resurse / bim_deviz / raport / export_excel / document /
  assignment / santier routes untouched
- Activity / Timesheet / Contract / Gantt / Commercial services + routes untouched
- models.py / migrations / templates / static / frontend untouched
```

Files changed in ed2c780:

```text
services/project_service.py (new)
routes/proiecte.py
tests/unit/test_project_service.py (new)
```

S1.3B summary:

```text
- create/edit/status save logic extracted to services/project_service.py
- create_project_from_form_data(), update_project_from_form_data(),
  change_project_status() added; private _compose_project_location() and
  _validate_project_manager() added
- adauga / editeaza / schimba_status valid-save branches delegate to the service
- route owns ProiectForm, validate_on_submit, request.form/get_json, flash,
  redirect, url_for, render_template, jsonify, HTTP codes
- auto cod_proiect GET pre-fill (global Proiect.query count) remains route-owned, unchanged
- editeaza GET locatie split remains route-owned, unchanged
- invalid schimba_status stays non-exception route-owned JSON 400
  ({'success': False, 'error': 'Status invalid'}); no mutation/commit
- service-commit / route-rollback convention applied (each mutator commits once;
  route wraps service calls in HTTPException/Exception -> rollback; raise)
- create resolves tenant_id via tenant_id_for_new_record_or_403() (fail-closed);
  edit/status operate on the route's get_project_or_404() object (foreign -> 404)
- manager validation via query_users_for_tenant().first_or_404() (no blind trust)
- finalizat sets data_sfarsit_real only when unset; existing value not overwritten
- no raw Proiect/Pontaj/Angajat/RaportActivitate.query introduced in the service
- forms/proiecte_forms.py untouched (its global queries preserved)
- lista / S1.3A read/list + financial helpers untouched
- detalii / hub / nested resources / raport / export_excel untouched
- Contract / Commercial / Gantt / Activity / Timesheet untouched
- models / migrations / templates / static / frontend untouched
```

Files changed in a9fabfc:

```text
services/project_service.py
routes/proiecte.py
tests/unit/test_project_service.py
```

Test-fixture note (S1.3B): tests/unit/test_project_service.py _curata cleanup was
broadened from 'S13A-%' to 'S13%' so S1.3B-created projects are also removed; and
the S1.3A HTTP-free/read-only guard was scoped to the read-only functions (the new
mutators legitimately commit). Test-only, behavior-preserving, validated by the full suite.

S1.4A summary:

```text
- get_project_detail_context() added to services/project_service.py (read-only)
- detalii read-only context assembly extracted to the project service
- detalii route delegates context assembly to the service; route keeps
  get_project_or_404, request.args (luna/anul), render_template, HTTP behavior
- service now owns: team assignments (ordered), active assigned + available
  employees, dist_functii, monthly pontaje, ore_per_angajat aggregate,
  total_ore / ore_saptamanale / cost_manopera / cost_lunar (via S1.3A helpers),
  legacy documents
- exact 14 detalii render-context values preserved (proiect/luna/anul route-owned)
- assignment ordering (data_sfarsit nullsfirst, data_start desc), angajati_activi
  (data_sfarsit None), available employees status='activ' ordered by nume,
  dist_functii fallback (functie_pe_proiect -> angajat.functie -> 'Necunoscut'),
  pontaje month/year filter + desc order, documents desc by data_upload preserved
- ore_per_angajat keeps its db.session.query aggregate, tenant-scoped via the
  query_timesheets_for_tenant() subquery (unchanged)
- service stays HTTP-free; S1.4A helper is read-only (no add/delete/commit/rollback)
- no new raw Proiect/Pontaj/Angajat/RaportActivitate/Document.query in the service
- query_employees_for_tenant + query_legacy_documents_for_tenant removed from
  routes/proiecte.py imports (now resolved inside the service)
- hub untouched and deferred; lista / adauga / editeaza / schimba_status /
  financial wrappers / nested / raport / export_excel untouched
- forms / models / migrations / templates / static / frontend untouched
- Contract / Commercial / Gantt / BIM / Activity / Timesheet untouched
```

Files changed in 4c15b01:

```text
services/project_service.py
routes/proiecte.py
tests/unit/test_project_service.py
```

Test-fixture note (S1.4A): _curata also deletes Document rows attached to S13%
projects (FK-orphan prevention); the read-only guard now includes
get_project_detail_context; the no-raw-query guard now also asserts Document.query
absent. Test-only, behavior-preserving, validated by the full suite (1178 passed).

Prior S1.2D1 summary (build_monthly_timesheet_export_data, export_lunar data
delegation, read-only HTTP-free helper) remains valid and untouched by S1.2D2.

The S1.1 activity service boundary (S1.1A–S1.1D) is complete and APPROVED by the
S1.C1 review (no P0/P1 blockers).
The S1.2A timesheet service read/list/context boundary is complete and validated.
The S1.2B1 timesheet single create/edit save boundary is complete and validated.
The S1.2B2 timesheet bulk create save boundary is complete and validated.
The S1.2C1 timesheet single workflow (trimite/aproba/respinge) is complete and validated.
The S1.2C2 timesheet bulk workflow (aproba_multiplu) is complete and validated.
The S1.2D1 timesheet monthly export data assembly (build_monthly_timesheet_export_data) is complete and validated.
The S1.2D2 timesheet import excel parsing/create (import_timesheets_from_rows) is complete and validated.
The S1.2 timesheet service boundary (S1.2A–S1.2D2) is complete and APPROVED by the S1.C2 review (no P0/P1 blockers).
The S1.3 Project Service no-code gate is APPROVED; S1.3A (project read/list + financial data assembly) is complete and validated in the new services/project_service.py.
The S1.3B project create/edit/status save boundary (create_project_from_form_data / update_project_from_form_data / change_project_status) is complete and validated.
The S1.3 Project Service boundary (S1.3A + S1.3B) is complete and APPROVED by the S1.C3 review (no P0/P1 blockers; see DECISIONS_LOG D017).
The S1.4 Project Details no-code gate is APPROVED; S1.4A (detalii read-only context, get_project_detail_context) is complete and validated. hub remains deferred.
The S1.4A Project Details context boundary is APPROVED by the S1.C4 review (no P0/P1 blockers; see DECISIONS_LOG D018).
The S1.5 Project Hub / Cross-Domain Aggregator no-code gate is complete. It
decided that hub should remain route-resident and that S1.5 implementation
should NOT be prepared. The Project service extraction line is effectively
complete for Project-owned surfaces after S1.3A, S1.3B, and S1.4A.

Approved Project service boundary:

```text
services/project_service.py owns Project-owned service logic:
- project read/list context
- project manager list / filtering / sorting / stats
- financial total hours / labor cost / weekly hours / monthly costs
- create/edit/status save logic
- detalii context through get_project_detail_context()
```

Route-owned / deferred Project surfaces:

```text
routes/proiecte.py keeps:
- hub cross-domain aggregator
- decorators
- request / render_template / flash / redirect / jsonify
- feature flags
- url_for / parcurs / next_idx
- nested resource routes
- raport/export_excel
- route/form global query behaviors intentionally preserved
- dead financial wrappers remain P3 cleanup only, removal not authorized
```

S1.5 hub decision:

```text
- hub is not Project-owned enough for services/project_service.py
- hub combines Contract, Commercial, Gantt, BIM, Location, Fleet, HR,
  Documents, feature flags, and navigation
- hub remains route-resident
- no S1.5 implementation next
- no project_hub_service implementation next
- separate cross-domain aggregator service is premature
- deeper hub tests are only required if extraction is reconsidered
```

Approved S1.2 boundary (S1.C2 / D016):

```text
- services/timesheet_service.py is the coherent, HTTP-free Pontaj/timesheet service boundary
- routes/pontaje.py keeps HTTP/upload/download/layout/flash/redirect/render/jsonify/send_file
- services/activity_service.py remains activity-only (D015 respected)
- no model/migration/template changes occurred during S1.2
- tenant safety preserved; behavior preserved; tests sufficient
- service-commit / route-rollback convention is consistent
```

Accepted deferrals / notes (S1.C2, P3/informational — cleanup NOT authorized):

```text
- sterge remains route-resident
- template_import remains route-resident (static workbook layout)
- export_lunar workbook layout + send_file remain route-owned
- import_excel request.files / load_workbook / flash / redirect remain route-owned
- _detect_tip_zi cleanup is not authorized (_detect_import_tip_zi duplicate accepted)
- get_project_employees_for_timesheet AngajatProiect.query is accepted (project
  validated tenant-safe first, employees re-filtered) as P3/informational
- docs/audits absent; CLAUDE.md roadmap stale (docs/ai + git authoritative)
```

---

## Review checkpoints

```text
S1.C1 Activity Service Extraction Review — APPROVED (no P0/P1)
S1.C2 Timesheet Service Extraction Review — APPROVED (no P0/P1)
S1.C3 Project Service Extraction Review — APPROVED (no P0/P1)
S1.C4 Project Details Context Extraction Review — APPROVED (no P0/P1)
S1.5 Project Hub / Cross-Domain Aggregator No-Code Gate — COMPLETED / HUB ROUTE-RESIDENT
Contract Core Read/List/Detail Service No-Code Gate — COMPLETED / NOT APPROVED FOR EXTRACTION DUE TO P1
```

S1.C1 findings (see DECISIONS_LOG D015):

```text
- P2: standardize the commit/rollback ownership convention during/around S1.2
      (service currently commits, route wrapper owns rollback)
- P2: S1.2 timesheet must use a NEW file services/timesheet_service.py,
      not services/activity_service.py
- P3: export_edifico/export_edifico_preview intentionally deferred in routes
- P3: sterge (activity delete) unextracted and acceptable
```

S1.C2 findings (see DECISIONS_LOG D016):

```text
- No P0/P1 blockers. S1.2 Timesheet Service Extraction APPROVED.
- P3: sterge / template_import accepted route-resident deferrals
- P3: export layout/send_file + import upload/load_workbook/flash/redirect route-owned
- P3: get_project_employees_for_timesheet AngajatProiect.query accepted
- P3: _detect_import_tip_zi duplicate accepted; cleanup not authorized
- Next service boundary (Project) must start with a no-code gate, not implementation
```

S1.C3 findings (see DECISIONS_LOG D017):

```text
- No P0/P1 blockers. S1.3 Project Service Extraction APPROVED (S1.3A/S1.3B).
- P3: detalii / hub / nested / report-export accepted route-resident deferrals
- P3: route auto-code Proiect.query + form validate_cod_proiect / __init__ global
      queries preserved (form-owned, overridden by _populeaza_manageri_form)
- P2: auto-code generation + editeaza GET locatie split lack direct tests (route-owned)
- Next Project surface (detalii/hub cross-domain) must start with an S1.4 no-code gate
```

S1.C4 findings (see DECISIONS_LOG D018):

```text
- No P0/P1 blockers. S1.4A Project Details Context Extraction APPROVED.
- hub byte-identical to BASE (untouched, deferred); detalii route keeps
  get_project_or_404 / request.args / render_template
- ore_per_angajat aggregate accepted (tenant-scoped via query_timesheets_for_tenant subquery)
- P3: route financial wrappers (_get_total_ore etc.) now dead code; removal NOT authorized
- Next Project surface (hub cross-domain aggregator) must start with an S1.5 no-code gate
```

S1.5 findings (see DECISIONS_LOG D019):

```text
- No P0/P1 blockers. hub is read-only, tenant-guarded, and mutates/commits nothing.
- hub uses get_project_or_404(id), tenant-safe query helpers, feature flag checks,
  and url_for/parcurs/next_idx route-owned presentation logic.
- hub is a cross-domain navigation/presentation aggregator, not Project-owned service logic.
- services/project_service.py must not absorb hub.
- separate cross-domain aggregator service is premature.
- S1.5 implementation should NOT be prepared; hub remains route-resident.
- Project service extraction line is effectively complete for Project-owned surfaces.
```

Contract Core Read/List/Detail findings (see DECISIONS_LOG D022):

```text
- P0 none.
- P1 present: render-time child queries in contract list/detail are not
  explicitly tenant-scoped.
- templates/contracte/detalii.html performs unscoped lazy queries for
  contract.programe_referinta, contract.oferte, and o.pozitii.count().
- routes/contracte.py::detalii and templates/contracte/lista.html use
  acte_aditionale relationship queries/counts without explicit tenant scoping.
- Contract Core service extraction is not approved yet.
- Next authorized task is T1.5D Contract List/Detail Render-Time Child Tenant Guard.
```

T1.5D Review findings (see DECISIONS_LOG D023):

```text
- P0 none.
- P1 none.
- 2fb137f T1.5D contract render child tenant guard reviewed and approved.
- original render-time lazy child tenant-safety blockers are fixed.
- contract list addendum counts are explicitly tenant-scoped before render.
- contract detail child collections/counts are explicitly tenant-scoped before render.
- flagged template lazy relationship access was removed for:
  - c.acte_aditionale.count()
  - contract.programe_referinta
  - contract.oferte
  - o.pozitii.count()
- strict / optional-with-tenant / off behavior verified.
- full suite passed: 1188 passed, 39 skipped, 4 warnings.
- Contract Core service extraction may resume only through a post-fix no-code gate.
```

---

## Current task

```text
Contract Core Read/List/Detail Post-T1.5D Service Boundary Re-Gate
```

Read-only no-code gate for Contract core read/list/detail after T1.5D.

Contract Service implementation is NOT authorized. Commercial / SituatieLunara
implementation is NOT authorized. No `services/contract_service.py` may be
created until the post-fix gate is reviewed and approved.

The previous completed review was T1.5D Review. It approved the fix for
Contract Core list/detail render-time child tenant-safety blockers.

## Constraints for the S1.x service extraction line (per D014 + D015)

- Extract one domain's behavior only.
- No schema changes.
- Preserve workflows and statuses.
- MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use tenant_access.py helpers.
- No raw RaportActivitate/Pontaj/Proiect/Angajat/BIM lookups in new service code.
- Add direct service-level tests.
- S1.2 timesheet logic goes in a NEW services/timesheet_service.py (D015).

## Next recommended work

```text
Contract Core Read/List/Detail Post-T1.5D Service Boundary Re-Gate
```

This is a read-only no-code gate:

```text
- confirm original list/detail P1 blockers are closed
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

Explicitly deferred until a future approved prompt:

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

Remaining / deferred Project work (each its own future gate if/when authorized):

```text
hub (360 cross-domain aggregator) — route-resident by S1.5 decision
nested resource routes (utilaje/resurse/documente/santier/angajat assignment) — deferred
reports/export (raport, export_excel) — deferred
Contract / Commercial / Gantt extraction — deferred to later domain-specific gates
```

Alternative future options:

```text
Contract Core List Context Extraction (only after post-T1.5D re-gate approval)
Contract Core Detail Context Extraction (only after post-T1.5D re-gate approval)
Contract Core C1A/C1B split
Contract core create/edit/delete save extraction (deferred)
Contract term/milestone extraction (deferred)
Commercial / SituatieLunara sub-gate
Oferta / BoQ sub-gate
Claims / Revendicari sub-gate
PV/export/reporting sub-gate
Gantt Service No-Code Gate
S1.x Service Boundary Hardening Gate
Project hub deep-test/hardening only if Albert explicitly wants to revisit hub
```

template_import remains route-resident because it is static workbook layout with
no domain extraction needed (per the S1.2D gate analysis).

sterge (timesheet delete) remains route-resident unless a future explicit task
says otherwise.

Accepted deferral (D015): export_edifico / export_edifico_preview and their data
helpers remain route-resident because those data helpers are co-called by layout
helpers; they are already tenant-safe.

---

## Current repository posture

Route-level tenant guard complete after T1.14.
Activity service boundary covers read/form context (S1.1A), create/edit save (S1.1B), workflow transitions (S1.1C), and report/export data assembly (S1.1D).
Timesheet service boundary now covers read/list/context and pure hour
calculation (S1.2A), single Pontaj create/edit saves (S1.2B1), bulk
Pontaj create saves (S1.2B2), single workflow transitions trimite/aproba/respinge
(S1.2C1), bulk workflow aproba_multiplu (S1.2C2), monthly export data assembly
for export_lunar (S1.2D1), and import Excel parsing/create for import_excel
(S1.2D2). The export_lunar workbook layout + send_file stay route-owned;
import_excel keeps request.files / extension validation / load_workbook /
flash / redirect route-owned. template_import stays route-resident (static
layout, no extraction); sterge stays route-resident. The S1.2 timesheet service
extraction line is complete and APPROVED by S1.C2 (D016).
Project service boundary (NEW services/project_service.py) now covers read/list
context + read-only financial data assembly for the lista route (S1.3A) AND
create/edit/status save for adauga / editeaza / schimba_status (S1.3B). The route
keeps ProiectForm / validate_on_submit / request / flash / redirect / render /
jsonify / HTTP codes, the auto cod_proiect GET pre-fill, and the editeaza GET
locatie split; service-commit / route-rollback applies to the mutating saves; the
invalid-status path stays a route-owned JSON 400. The S1.3 Project Service
extraction (S1.3A + S1.3B) is complete and APPROVED by S1.C3 (D017). The detalii
read-only context assembly is now in the service too (S1.4A,
get_project_detail_context, APPROVED by S1.C4 / D018); the detalii route keeps
get_project_or_404 / request.args / render_template. hub and the remaining
cross-domain project routes (nested resources, raport, export_excel) remain
route-resident pending later gates. S1.5 decided hub remains route-resident, so
Project service extraction is complete for Project-owned surfaces.

Contract / Commercial is the next domain family, but implementation is still not
directly authorized. The responsible-user tenant/input P1 is closed by b519d51
and approved by T1.5C Review. The Contract Core list/detail render-time child
tenant-safety P1 is closed by 2fb137f and approved by T1.5D Review.
Project service extraction remains complete for Project-owned surfaces.
Contract Core service extraction may resume only through a post-fix
Contract Core Read/List/Detail no-code re-gate that decides the exact
C1A/C1B implementation split. Broad Contract / Commercial, Commercial /
SituatieLunara, Oferta / BoQ, Claims / Revendicari, and PV/export/reporting
extraction remain deferred.

Remaining accepted future categories:

```text
service-boundary hardening
historical data contamination cleanup
schema improvements for indirect ownership models
direct service tests for extracted services
```
