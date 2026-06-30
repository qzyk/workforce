# PROJECT_STATE.md — Canonical Project State for AI Agents

Last updated after:

```text
S1.C3 Project Service Extraction Review — APPROVED
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
feat/s1.3b-project-create-edit-status-extraction
```

## Current canonical HEAD

```text
a9fabfc S1.3B project create edit status extraction
```

## Current test baseline

S1.3B VALIDATED.

```text
project service unit tests (tests/unit/test_project_service.py): 34 passed (19 S1.3A + 15 S1.3B)
project targeted suite (service + project route/nested/hub/locations): 69 passed
regression safety (activity + timesheet + timesheet routes): 150 passed
Flask app smoke (proiecte routes): ok 27
full suite (tests/unit + tests/integration): 1167 passed, 39 skipped, 4 warnings
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
```

Latest completed service extraction step:

```text
S1.3B Project Create/Edit/Status Save Extraction
(reviewed and APPROVED by S1.C3)
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

---

## Current task

```text
S1.4 Project Details / Cross-Domain Context No-Code Gate
```

Read-only understanding / collision-safety gate for the Project detalii + hub
cross-domain context (routes/proiecte.py). Produces a no-code report only.

S1.4 IMPLEMENTATION IS NOT AUTHORIZED. Project detalii/hub extraction may start
only after this no-code gate is reviewed and approved by Albert.

Alternative future options (only if Albert chooses a different sequence):
Contract/Commercial Service no-code gate, Gantt Service no-code gate, or an
S1.x Service Boundary Hardening Gate. The current authorized task is the S1.4
Project detalii/hub cross-domain no-code gate.

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
S1.4 Project Details / Cross-Domain Context No-Code Gate (current authorized task — no-code)
```

S1.3 Project Service Extraction (S1.3A + S1.3B) is complete and APPROVED by S1.C3
(D017). The next Project surface (detalii + hub cross-domain context) must begin
with the S1.4 no-code gate, NOT implementation.

Remaining / deferred Project work (each its own future gate if/when authorized):

```text
detalii cross-domain context — S1.4 gate (current)
hub (360 cross-domain aggregator) — S1.4 gate (current)
nested resource routes (utilaje/resurse/documente/santier/angajat assignment) — deferred
reports/export (raport, export_excel) — deferred
Contract / Commercial / Gantt extraction — deferred to later domain-specific gates
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
extraction (S1.3A + S1.3B) is complete and APPROVED by S1.C3 (D017). All
cross-domain project routes (detalii, hub, nested resources, raport, export_excel)
remain route-resident pending later gates. The next authorized task is the S1.4
Project Details / Cross-Domain Context no-code gate (detalii + hub; no
implementation until reviewed and approved by Albert).

Remaining accepted future categories:

```text
service-boundary hardening
historical data contamination cleanup
schema improvements for indirect ownership models
direct service tests for extracted services
```
