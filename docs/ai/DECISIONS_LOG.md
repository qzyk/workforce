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
