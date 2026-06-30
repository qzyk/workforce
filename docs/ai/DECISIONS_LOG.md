# DECISIONS_LOG.md — Edifico Architectural and Security Decisions

This file records decisions that Claude Code must preserve.

If a task conflicts with this file, stop and ask for clarification.

---

## D001 — Product identity

Edifico / EDIFICO WORKFORCE is a Construction Operating System / construction execution layer.

It is not a BIM clone, not a Solibri clone, and not a pure planning tool.

---

## D002 — Execution spine

The canonical execution spine is:

```text
Company / Tenant
→ Project
→ ProgramReferinta
→ TaskProgram
→ RaportActivitate
→ Pontaj
→ SituatieLunara
```

---

## D003 — BIM role

BIM is a context layer only.

BIM must not become the source of truth for execution.

BIM context may enrich activities, timesheets, quantities, issues, and location data, but it must not replace the execution spine.

---

## D004 — Activity meaning

`RaportActivitate` is proof of executed work.

It is the main operational proof-of-work record.

---

## D005 — Timesheet meaning

`Pontaj` is labor/time/cost truth.

It should be linked to project/employee context and later integrated with service boundaries carefully.

---

## D006 — TaskProgram meaning

`TaskProgram` becomes the operational task after an approved plan/baseline is promoted.

Do not create a new `ExecutionTask` model now.

---

## D007 — Service extraction timing

Do not start service extraction until route-level tenant guard is clean.

Current required blocker before service extraction:

```text
T1.14 Activity BIM Context Tenant Guard
```

Only after T1.14 and T1.C14 are clean may the project start:

```text
S1.1 Activity Service Extraction
```

---

## D008 — No architectural rewrite

Do not introduce:

- microservices;
- frontend rewrite;
- Celery/Redis;
- event bus;
- workflow engine;

unless explicitly approved in a future task.

Current product remains Flask + SQLAlchemy + Alembic + server-rendered templates + modular monolith.

---

## D009 — Tenant guard policy

For tenant-aware tasks:

- preserve `MULTI_TENANT_MODE=off`;
- support `optional`;
- fail closed in `strict`;
- normal users without tenant fail closed in strict mode;
- foreign IDs return 404 where possible;
- super-admin without tenant remains explicit/global where intended;
- use `services/security/tenant_access.py`.

---

## D010 — No schema changes during T1.x unless explicitly approved

T1.x tenant guard PRs should not add migrations or schema changes.

Indirect ownership is handled through helper functions.

Historical data contamination is hidden/excluded by tenant guards, not repaired during T1.x.

---

## D011 — External Claude worktrees

Claude worktrees under:

```text
/Users/albertciolacu/workforce/.claude/worktrees/
```

are external non-authoritative experimental worktrees.

They must not be used as source of truth.

Do not merge, delete, clean, or copy from them unless a future explicit task says so.

---

## D012 — Canonical worktree

Canonical implementation work happens in:

```text
/Users/albertciolacu/workforce-t1.5-contract
```

Do not work in:

```text
/Users/albertciolacu/workforce
```

---

## D013 — T1.C13 decision

T1.C13 reviewed the canonical branch after T1.13 and concluded:

```text
Tenant guard phase is mostly complete, but one more tenant guard PR is needed first.
```

Required next PR:

```text
T1.14 Activity BIM Context Tenant Guard
```

Reason:

```text
Activity BIM context still has raw dropdown/filter/save lookups and BIM element detail has raw activity/timesheet aggregates.
```

---

## D014 — S1.1 constraints once approved

When S1.1 Activity Service Extraction is approved, it must:

- extract activity behavior only;
- avoid schema changes;
- preserve workflows and statuses;
- keep `MULTI_TENANT_MODE=off` compatible;
- fail closed in strict mode;
- use `tenant_access.py` helpers;
- avoid raw `RaportActivitate`, `Pontaj`, `Proiect`, `Angajat`, or BIM context lookups;
- add direct service-level tests.

---

## D015 — S1.C1 review outcome and S1.2 directives

S1.C1 reviewed the completed S1.1 activity service boundary (S1.1A–S1.1D) and
concluded:

```text
APPROVED. No P0/P1 blockers.
services/activity_service.py is a coherent activity-domain service boundary.
Tenant safety and existing behavior preserved; tests sufficient.
```

Decisions recorded for the next steps:

- **One service file per domain.** S1.2 Timesheet Service Extraction must use a
  NEW file `services/timesheet_service.py`, NOT `services/activity_service.py`.
  Do not bloat the activity service with timesheet logic.
- **Transaction convention.** The current activity boundary uses a split
  convention (service performs `db.session.commit()`, route wrapper owns
  rollback). Standardize the commit/rollback ownership convention during or
  around S1.2 so service boundaries are consistent. This is P2 cleanup, not a
  blocker.
- **Accepted deferrals (do not treat as bugs):**
  - `export_edifico` / `export_edifico_preview` and their data helpers remain
    route-resident for layout stability (their data helpers are co-called by
    layout helpers); they are already tenant-safe.
  - `sterge` (activity delete) remains unextracted and is acceptable.
- **T1.C14 invariant.** Monthly report/export timesheet data must stay scoped
  via `query_timesheets_for_tenant()`; never reintroduce raw `Pontaj.query`.

S1.2 implementation is NOT authorized by this decision. It requires an S1.2
no-code safety gate reviewed and approved by Albert.

---

## D016 — S1.C2 Timesheet Service Extraction Review outcome

S1.C2 reviewed the completed S1.2 timesheet service boundary
(S1.2A → S1.2B1 → S1.2B2 → S1.2C1 → S1.2C2 → S1.2D1 → S1.2D2) and concluded:

```text
S1.2 Timesheet Service Extraction — APPROVED. No P0/P1 blockers.
services/timesheet_service.py is a coherent, HTTP-free Pontaj/timesheet service.
Tenant safety and existing behavior preserved; tests sufficient.
```

Decisions recorded:

- **Approved boundary.** `services/timesheet_service.py` is the approved
  Pontaj/timesheet service boundary. `routes/pontaje.py` remains the
  HTTP/orchestration boundary (upload/download/flash/redirect/render/jsonify/
  send_file).
- **Commit/rollback convention.** The service-commit / route-rollback convention
  is consistent and is the standing convention for the S1.x service line:
  mutating service helpers call `db.session.commit()`; route wrappers own
  `db.session.rollback()` on `HTTPException` and unexpected `Exception`.
- **Accepted route-resident deferrals (do not treat as bugs):**
  - `sterge` (timesheet delete) remains route-resident.
  - `template_import` remains route-resident (static workbook layout, no domain
    logic to extract).
  - `export_lunar` workbook layout + `send_file` remain route-owned (only the
    tenant-scoped data assembly was extracted into
    `build_monthly_timesheet_export_data`).
  - `import_excel` request.files / `.xlsx` validation / `load_workbook` / flash /
    redirect remain route-owned (only row-processing/create was extracted into
    `import_timesheets_from_rows`).
- **Tenant invariants preserved.** No new raw `Pontaj/Angajat/Proiect/
  RaportActivitate.query` in tenant-aware service code. The only `Pontaj.query.get`
  is the isolated off-mode legacy branch of `bulk_approve_timesheets` (T1.4
  pattern). `import_excel` intentionally does NOT use
  `tenant_id_for_new_record_or_403()` or `require_timesheet_inputs_same_tenant()`
  (those would convert per-row skip into `abort(404)`). Monthly export data stays
  scoped via `query_timesheets_for_tenant()`.
- **P3 / informational (cleanup NOT authorized):**
  - `get_project_employees_for_timesheet` uses `AngajatProiect.query` after
    tenant-safe project validation + employee re-filtering — accepted.
  - `_detect_import_tip_zi` duplicates the route `_detect_tip_zi`; the route
    helper is now effectively dead but cleanup is not authorized.
  - `docs/audits/` are absent in this canonical worktree; CLAUDE.md roadmap is
    stale. `docs/ai/*` + git history remain authoritative.
- **Next boundary must start with a no-code gate.** The next service boundary
  (Project Service) must begin with an S1.3 no-code understanding / collision
  safety gate reviewed and approved by Albert — NOT direct implementation.

S1.3 implementation is NOT authorized by this decision. It requires an S1.3
no-code safety gate reviewed and approved by Albert.

---

## D017 — S1.C3 Project Service Extraction Review outcome

S1.C3 reviewed the completed S1.3 Project Service boundary (S1.3A read/list +
financial data assembly; S1.3B create/edit/status save) and concluded:

```text
S1.3 Project Service Extraction — APPROVED for the S1.3A/S1.3B boundary.
No P0/P1 blockers.
services/project_service.py is a coherent, HTTP-free Project service.
Tenant safety and existing behavior preserved; tests sufficient.
```

Decisions recorded:

- **Approved boundary.** `services/project_service.py` is the approved Project
  service boundary for: manager list / list context; filtering / search / sort /
  pagination / stats; financial total hours / labor cost / weekly hours / monthly
  costs; create save; edit save; status transition. `routes/proiecte.py` remains
  the HTTP/orchestration boundary (decorators, request args/form/json, ProiectForm
  + validate_on_submit, _populeaza_manageri_form, auto cod_proiect GET pre-fill,
  editeaza GET locatie split, render/flash/redirect/jsonify, invalid-status 400).
- **Commit/rollback convention.** Read-only helpers stay read-only; mutating
  helpers (`create_project_from_form_data`, `update_project_from_form_data`,
  `change_project_status`) commit exactly once; the route owns rollback wrappers
  on the mutating branches. Invalid `schimba_status` stays a non-exception JSON 400.
- **Accepted route-resident deferrals (do not treat as bugs):**
  - `detalii` cross-domain context remains route-resident.
  - `hub` cross-domain aggregator remains route-resident.
  - nested resource routes (utilaje / resurse / documente / santier links /
    employee assignments) remain route-resident.
  - `raport` / `export_excel` remain route-resident.
  - Contract / Commercial / Gantt / BIM remain deferred to later domain gates.
- **Pre-existing global queries preserved (P3, cleanup NOT authorized):**
  - route auto-code `Proiect.query` global count (GET pre-fill).
  - `ProiectForm.validate_cod_proiect` global `Proiect.query` uniqueness.
  - `ProiectForm.__init__` global `Utilizator.query`, overridden by
    `_populeaza_manageri_form`.
- **P2 / informational (non-blocking):** auto cod_proiect generation and the
  editeaza GET locatie split lack direct test coverage but are route-owned and
  unchanged; `docs/audits/` absent; CLAUDE.md roadmap stale (docs/ai + git
  authoritative).
- **Next boundary must start with a no-code gate.** The next Project surface
  (detalii / hub cross-domain context) must begin with an S1.4 no-code gate
  reviewed and approved by Albert — NOT direct implementation.

S1.4 implementation is NOT authorized by this decision. It requires an S1.4
no-code safety gate reviewed and approved by Albert.

---

## D018 — S1.C4 Project Details Context Extraction Review outcome

S1.C4 reviewed the completed S1.4A Project Details context extraction (detalii
read-only context assembly into services/project_service.py) and concluded:

```text
S1.4A Project Details Context Extraction — APPROVED. No P0/P1 blockers.
get_project_detail_context() is a coherent, additive, HTTP-free, read-only,
tenant-safe Project-details context helper; detalii behavior preserved.
```

Decisions recorded:

- **Approved helper.** `get_project_detail_context()` is the approved Project
  details context helper in `services/project_service.py` (read-only, HTTP-free,
  additive; S1.3A/S1.3B helper bodies unchanged).
- **Route ownership.** `routes/proiecte.py::detalii` keeps `get_project_or_404(id)`,
  `request.args` (luna/anul), `render_template('proiecte/detalii.html', ...)`, and
  HTTP behavior. The service returns plain data only.
- **hub remained untouched and is explicitly deferred** (byte-identical to BASE).
  hub must not be absorbed into project_service without a separate S1.5 no-code gate.
- **Tenant safety.** The `ore_per_angajat` `db.session.query` aggregate is accepted
  ONLY because it is tenant-scoped through the `query_timesheets_for_tenant()`
  subquery (preserved exactly). No raw `Proiect/Pontaj/Angajat/RaportActivitate/
  Document.query` introduced in the service.
- **P3 / informational (cleanup NOT authorized):** the route financial wrappers
  `_get_total_ore` / `_calculeaza_cost_manopera` / `_get_ore_saptamanale` /
  `_get_cost_lunar` appear to be dead code now that `detalii` calls the S1.3A
  service helpers via `get_project_detail_context()` — do NOT remove without
  separate approval. `docs/audits/` absent; CLAUDE.md roadmap stale (docs/ai +
  git authoritative).
- **Next Project surface must start with a no-code gate.** `hub` (the Project 360
  cross-domain aggregator) must begin with an S1.5 no-code understanding /
  collision-safety gate reviewed and approved by Albert — NOT direct implementation.

S1.5 implementation is NOT authorized by this decision. It requires an S1.5
no-code safety gate reviewed and approved by Albert.

---

## D019 — S1.5 Project Hub / Cross-Domain Aggregator Gate outcome

S1.5 reviewed the Project Hub / Cross-Domain Aggregator surface in
`routes/proiecte.py` and concluded:

```text
S1.5 Project Hub / Cross-Domain Aggregator No-Code Gate — COMPLETED.
No P0/P1 blockers.
hub should remain route-resident.
S1.5 implementation should NOT be prepared.
```

Decisions recorded:

- **hub is read-only and tenant-guarded.** It uses `get_project_or_404(id)` and
  tenant-safe query helpers before rendering the Project 360 / hub view. It has
  no raw-query risk identified by the S1.5 gate, mutates nothing, commits
  nothing, and `_safe` fails closed to default/empty values.
- **hub is route-owned.** It is a cross-domain navigation/presentation
  aggregator, not Project-owned service logic. It combines Contract,
  Commercial / `SituatieLunara`, Gantt, BIM, Location, Fleet, HR, Documents,
  feature flags, `url_for`, `parcurs`, and `next_idx`.
- **Do not absorb hub into `services/project_service.py`.** The approved Project
  service boundary remains Project-owned: read/list context, manager list /
  filtering / sorting / stats, financial data assembly, create/edit/status save
  logic, and `get_project_detail_context()`.
- **Do not create a cross-domain aggregator service now.** A separate
  `project_hub_service` or cross-domain aggregator service is premature.
- **Project service extraction is complete for Project-owned surfaces.** The
  completed Project stack is S1.3A read/list + financial data assembly, S1.3B
  create/edit/status save, and S1.4A `detalii` context.
- **Accepted Project route-resident deferrals (do not treat as bugs):**
  - hub remains route-resident;
  - nested resource routes remain route-resident;
  - `raport` / `export_excel` remain route-resident;
  - dead financial wrappers from S1.C4 are P3 cleanup only and removal is not
    authorized.
- **Testing posture.** hub test coverage is smoke-level only, acceptable while
  hub remains route-resident. Deeper hub tests are required only if extraction
  is reconsidered.
- **Next domain should start with a no-code gate.** Recommended next task:

```text
Contract / Commercial Service No-Code Gate
```

Contract / Commercial implementation is NOT authorized by this decision. It
requires a no-code understanding / collision-safety gate reviewed and approved
by Albert.

---

## D020 — Contract / Commercial No-Code Gate outcome

The Contract / Commercial Service No-Code Understanding / Collision Safety Gate
reviewed `routes/contracte.py`, the existing contract/commercial services, tenant
helpers, tests, and cross-domain collision risks.

Gate outcome:

```text
Contract / Commercial Service No-Code Gate — COMPLETED.
P0: none.
P1: present.
Contract / Commercial service extraction is NOT approved yet.
```

P1 blocker:

- `forms/contract_forms.py::TermenContractForm.responsabil_id` currently
  exposes all active users through raw `Utilizator.query`.
- `routes/contracte.py::termen_nou` and `routes/contracte.py::termen_editeaza`
  can save `responsabil_id` without same-tenant validation.
- This can leak users and allow cross-tenant responsible assignment.

Decisions recorded:

- **Do not start Contract / Commercial service extraction yet.**
- **Do not create `services/contract_service.py` yet.**
- **Do not modify `services/situatii.py` or other commercial/reporting services
  for extraction yet.**
- **Next implementation must be narrow and P1-focused.**
- The next authorized task is:

```text
T1.5C Contract Form/Input Tenant Guard Hardening
```

T1.5C scope:

- fix tenant-safe `responsabil_id` choices;
- prevent cross-tenant responsible assignment;
- review related contract form dropdown leakage only if it fits the same small
  tenant/input hardening scope;
- no schema changes;
- no templates;
- no service extraction.

Accepted findings / deferrals:

- `routes/contracte.py` has broad route-level tenant safety through T1.5 helpers.
- No broad raw-query direct-access pattern was found in `routes/contracte.py`.
- Existing commercial/reporting services remain legacy functional services, not
  approved direct tenant-safe service boundaries:
  - `services/situatii.py`
  - `services/centralizator.py`
  - `services/rapoarte_lucrari.py`
  - `services/evm.py`
  - `services/deviz_pricing.py`
  - `services/conflict_revendicare.py`
  - `services/pv_generator.py`
- Contract core, Commercial/Situatie, Oferta/BoQ, Claims, PV/export/reporting
  extraction must remain deferred.

Contract / Commercial service extraction may resume only after T1.5C is
implemented, tested, and reviewed by Albert.

---

## D021 — T1.5C Contract Form/Input Tenant Guard Review outcome

T1.5C implemented the narrow Contract term responsible-user tenant/input hardening
in:

```text
b519d51 T1.5C contract term responsible tenant guard
```

The T1.5C review concluded:

```text
T1.5C Review — Contract Form/Input Tenant Guard Hardening Review
APPROVED
P0: none
P1: none
```

Decisions recorded:

- **Original P1 fixed.** `TermenContractForm.responsabil_id` no longer exposes all
  active users through raw `Utilizator.query`.
- **Form choices are tenant-scoped.** Responsible-user dropdown choices are built
  through tenant-safe `query_for_tenant(Utilizator)` behavior, inactive users
  remain excluded, and the empty/no-responsible option is preserved.
- **Route input validation added.** `routes/contracte.py::termen_nou` and
  `routes/contracte.py::termen_editeaza` validate submitted `responsabil_id`
  before save.
- **Foreign responsible assignment is blocked.** A foreign tenant responsible
  user cannot be persisted on `TermenContract.responsabil_id`; `responsabil_id=0`
  still maps to `None`; valid same-tenant responsible assignment still works.
- **No broad extraction occurred.** No schema, model, template, service
  extraction, Project service, Project hub, or Contract / Commercial extraction
  changes occurred.
- **Tests passed.** T1.5C review validation included:

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

Contract / Commercial service extraction can resume only through a narrow
no-code gate reviewed and approved by Albert. Direct Contract Service
implementation is not authorized by this decision. Commercial / SituatieLunara
implementation is not authorized by this decision.

Next recommended authorized task:

```text
Contract Core Read/List/Detail Service No-Code Gate
```

That next gate is read-only and should focus only on `routes/contracte.py`
Contract core read/list/detail surfaces (`lista`, `detalii`, and related
context helpers). It must not create `services/contract_service.py`; must not
start create/edit/delete extraction; and must defer terms/milestones,
Commercial/SituatieLunara, Oferta/BoQ, Claims/Revendicari, PV/export/reporting,
Gantt, BIM, Activity, Timesheet, schema, migrations, templates, frontend, and
route URL changes.

---

## D022 — Contract Core Read/List/Detail Gate outcome

The Contract Core Read/List/Detail Service No-Code Gate reviewed the narrow
contract list/detail surfaces after T1.5C.

Gate outcome:

```text
Contract Core Read/List/Detail Service No-Code Gate — COMPLETED.
P0: none.
P1: present.
Contract Core service extraction is NOT approved yet.
```

P1 blockers:

- `templates/contracte/detalii.html` performs unscoped render-time lazy queries:
  - `contract.programe_referinta`
  - `contract.oferte`
  - `o.pozitii.count()`
- `routes/contracte.py::detalii` and `templates/contracte/lista.html` use
  `acte_aditionale` relationship queries/counts without explicit tenant scoping.

Risk:

```text
These child models have tenant ownership and can leak under historical/corrupted
cross-tenant links.
```

Decisions recorded:

- **Do not start Contract Core service extraction yet.**
- **Do not create `services/contract_service.py` yet.**
- **Do not start Commercial / SituatieLunara extraction yet.**
- **Do not extract `lista` / `detalii` yet.**
- **First fix the render-time child tenant-safety P1.**

The next authorized task is:

```text
T1.5D Contract List/Detail Render-Time Child Tenant Guard
```

T1.5D scope:

- tenant-scope render-time child collections/counts for contract list/detail;
- prevent template lazy relationship queries from bypassing tenant helpers;
- add tests proving cross-tenant child rows attached to a valid tenant-owned
  parent are hidden;
- no service extraction;
- no commercial workflow changes;
- no schema changes;
- no models/migrations;
- no broad template redesign.

Contract Core service extraction may resume only after T1.5D is completed,
tested, and reviewed by Albert.

---

## D023 — T1.5D Contract List/Detail Render-Time Child Tenant Guard Review outcome

T1.5D implemented the narrow Contract list/detail render-time child tenant guard
in:

```text
2fb137f T1.5D contract render child tenant guard
```

The T1.5D review concluded:

```text
T1.5D Review — Contract List/Detail Render-Time Child Tenant Guard Review
APPROVED
P0: none
P1: none
```

Decisions recorded:

- **Original P1 fixed.** The render-time lazy child tenant-safety blockers found
  by the Contract Core Read/List/Detail gate are fixed.
- **Contract list protected.** Addendum counts for `contracte/lista.html` are
  now computed explicitly through tenant-scoped route context before render.
- **Contract detail protected.** Detail child collections/counts are now
  computed explicitly through tenant-scoped route context before render for
  addenda, `ProgramReferinta`, `OfertaContract`, and `PozitieBoQ` counts.
- **Flagged template lazy access removed.** The implementation removed direct
  template lazy access for:
  - `c.acte_aditionale.count()`
  - `contract.programe_referinta`
  - `contract.oferte`
  - `o.pozitii.count()`
- **Tenant modes verified.** Strict mode hides/counts only same-tenant children;
  optional mode with tenant hides foreign child rows; off mode preserves legacy
  unfiltered behavior through existing tenant helper semantics.
- **No broad extraction occurred.** No `services/contract_service.py` was
  created, no Contract Service implementation was started, and no Commercial /
  SituatieLunara implementation was started.
- **No unrelated surfaces changed.** No schema, model, form, service, Project
  service, Project hub, Gantt, BIM, Activity, Timesheet, static, or frontend
  changes occurred.
- **Tests passed.** T1.5D review validation included:

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

Contract Core service extraction may resume only through a post-fix no-code gate
reviewed and approved by Albert. Direct Contract Service implementation is not
authorized by this decision. Commercial / SituatieLunara implementation is not
authorized by this decision.

Next recommended authorized task:

```text
Contract Core Read/List/Detail Post-T1.5D Service Boundary Re-Gate
```

That next gate is read-only and should decide whether the first safe
implementation slice should be C1A Contract Core List Context Extraction, C1B
Contract Core Detail Context Extraction, a C1A/C1B split sequence, or additional
no-code/test hardening. It must not create `services/contract_service.py`; must
not start create/edit/delete extraction; and must defer terms/milestones,
Commercial/SituatieLunara, Oferta/BoQ, Claims/Revendicari, PV/export/reporting,
Gantt, BIM, Activity, Timesheet, schema, migrations, templates, frontend, and
route URL changes.

---

## D024 — Contract Core Post-T1.5D Re-Gate outcome

The Contract Core Read/List/Detail Post-T1.5D Service Boundary Re-Gate reviewed
the narrow contract list/detail surfaces after T1.5C and T1.5D.

The gate concluded:

```text
Contract Core Read/List/Detail Post-T1.5D Service Boundary Re-Gate — COMPLETED
P0: none
P1: none
```

Decisions recorded:

- **T1.5C blocker remains closed.** The responsible-user tenant/input P1 fixed
  by `b519d51 T1.5C contract term responsible tenant guard` remains closed.
- **T1.5D blocker remains closed.** The render-time child tenant-safety P1 fixed
  by `2fb137f T1.5D contract render child tenant guard` remains closed.
- **Contract list/detail are ready for planning.** Contract list/detail
  route-level tenant safety is sufficient for service-boundary planning.
- **First implementation slice is list-only.** The first safe implementation
  slice should be C1A Contract Core List Context Extraction.
- **Detail extraction is deferred.** C1B Contract Core Detail Context Extraction
  must wait until after C1A is implemented and reviewed.
- **No broad Contract Service extraction.** Broad Contract Service extraction is
  not approved.
- **No Commercial / SituatieLunara extraction.** Commercial / SituatieLunara
  extraction is not approved.
- **No unrelated extraction.** Create/edit/delete, term/milestone mutation,
  Oferta/BoQ, Claims/Revendicari, PV/export/reporting, Project service, Project
  hub, Gantt, BIM, Activity, Timesheet, schema, migrations, templates, frontend,
  and route URL changes remain out of scope for C1A.

Post-fix gate validation baseline:

```text
py_compile passed
contract targeted tests: 50 passed
broad tenant regression: 256 passed
project regression: 60 passed
activity/timesheet regression: 150 passed
Flask smoke: ok 365
worktree remained clean
```

Approved next authorized task:

```text
C1A Contract Core List Context Extraction
```

C1A scope constraints:

```text
- Contract core list context only
- read-only
- HTTP-free service helper
- route keeps request.args, decorators, feature gate, render_template, and HTTP behavior
- preserve status/project/search filters
- preserve main-contract-only behavior
- preserve stats counts
- preserve visible project choices
- preserve tenant-scoped addendum counts
- preserve template name contracte/lista.html and existing context keys
```

C1A must not include:

```text
contract detail extraction
templates/forms/models/migrations/static/frontend changes
create/edit/delete extraction
term/milestone mutation routes
PV/export/reporting
Commercial / SituatieLunara
Oferta / BoQ
claims/revendicari
Project service or Project hub changes
Gantt/BIM/Activity/Timesheet changes
route URL changes
```
