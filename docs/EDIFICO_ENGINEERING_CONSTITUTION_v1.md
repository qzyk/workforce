# 00 — Edifico Vision

## Product identity

Edifico is a **Construction Operating System**.

Edifico is not primarily:

- a BIM authoring tool;
- a Solibri competitor;
- a BIMcollab clone;
- an Autodesk Construction Cloud clone;
- a generic HR platform;
- a generic project management tool;
- an AI document generator.

Edifico exists to answer one operational question:

> What was planned, who was responsible, what was actually executed, what proof exists, what changed, what is delayed, and what is the business impact?

## North Star

The North Star is **execution truth**.

Every major feature must strengthen at least one of these:

1. planning clarity;
2. workforce accountability;
3. proof of work;
4. approval traceability;
5. delay visibility;
6. contract/commercial defensibility;
7. executive decision making;
8. tenant-safe B2B collaboration.

If a feature does not improve execution truth, it is not core.

## Product loop

The canonical product loop is:

```text
Project is created
  -> contractual or generated plan is attached
  -> ProgramReferinta becomes approved baseline
  -> TaskProgram represents planned work
  -> workforce is assigned
  -> work is reported through RaportActivitate
  -> time/cost is recorded through Pontaj
  -> evidence is attached
  -> supervisor/manager approves
  -> progress updates TaskProgram
  -> delay is detected or confirmed
  -> situation/claim/report is generated
  -> executive cockpit shows truth
```

## Strategic posture

Edifico should win where existing BIM tools are weak:

| Competitor category | They do well | Edifico should not compete there | Edifico should own |
|---|---|---|---|
| Solibri | model QA/QC and rule checking | geometric validation engines | execution accountability |
| BIMcollab | issue coordination | pure BCF issue hub | issue-to-field execution flow |
| BonsaiBIM | native IFC authoring | authoring/model editing | operational execution context |
| Autodesk/ACC | broad enterprise CDE | full ecosystem replacement | focused construction execution OS |
| Excel/MS Project | flexible planning | generic planning spreadsheets | plan-to-field-to-proof loop |

## What Edifico should become

Edifico should become the place where an owner, general contractor, project manager, site manager, subcontractor, planner, and commercial manager can answer:

- What is the approved plan?
- Which tasks are late?
- Who is responsible?
- What was done today?
- Which work has proof?
- Which reports are approved?
- Which costs are real?
- Which quantities are validated?
- Which delays can become claims?
- Which subcontractors are underperforming?
- Which decisions require intervention now?

## What must not happen

Edifico must not become a pile of disconnected modules.

Danger signs:

- BIM features that do not connect to execution;
- Gantt generation that does not become baseline/progress;
- reports generated from unscoped data;
- route functions with business logic;
- tenant checks implemented ad-hoc;
- AI-generated plans without real operational validation;
- duplicate status workflows;
- progress calculated differently in five places.

## Product law

> Execution is the core. Planning, BIM, contracts, reporting, workforce, and AI exist only to support execution.


---

# 01 — Non-Negotiable Decisions

These decisions are considered closed for v1.x unless a formal ADR changes them.

## Decision 001 — Product category

Edifico is a **Construction Operating System**.

It is not primarily a BIM tool.

### Consequences

- BIM must remain optional for normal execution workflows.
- The field user must be able to report work without opening a 3D model.
- BIM should enhance context, not block execution.

## Decision 002 — Execution spine

The execution spine is:

```text
Proiect
  -> ProgramReferinta
  -> TaskProgram
  -> RaportActivitate
  -> Pontaj
  -> SituatieLunara
```

### Consequences

- New operational work features must relate to this chain.
- `TaskProgram` becomes the operational planned task.
- `RaportActivitate` becomes executed-work proof.
- `Pontaj` becomes labor/time/cost support.
- `SituatieLunara` becomes commercial monthly truth.

## Decision 003 — No new `ExecutionTask` model now

Do not add a separate `ExecutionTask` model unless a future ADR proves `TaskProgram` is insufficient.

### Why

`TaskProgram` already has:

- project link;
- program link;
- WBS/code;
- planned dates;
- real dates;
- percentage;
- predecessors;
- relationship to contractual programs;
- future claim/report relevance.

Adding `ExecutionTask` now would create a third competing task source.

## Decision 004 — `GanttPlan` is not the execution backbone

`GanttPlan` remains a planning/generation/import/export artifact.

When a plan becomes operational, it should be promoted or mapped into `ProgramReferinta` and `TaskProgram`.

## Decision 005 — Tenant safety before feature development

No multi-company SaaS rollout is acceptable until tenant boundaries are enforced.

The system must fail closed in strict mode.

## Decision 006 — Route logic must shrink

Routes should not own business rules.

Target shape:

```text
route
  -> auth / request parsing
  -> service call
  -> response
```

Anti-pattern:

```text
route
  -> query
  -> validation
  -> calculations
  -> workflow transitions
  -> audit
  -> export rendering
```

## Decision 007 — Modular monolith

Keep the architecture as a modular monolith.

No microservices, no Celery/Redis requirement, no infrastructure that is hard to operate on PythonAnywhere.

## Decision 008 — PythonAnywhere compatibility

Every PR must preserve:

- WSGI compatibility;
- Flask app factory compatibility;
- SQLAlchemy + PyMySQL compatibility;
- Alembic compatibility;
- no long blocking request handlers;
- no mandatory background worker.

## Decision 009 — AI is later and advisory

AI must not approve work, change contracts, modify baseline, or create claims automatically.

AI may:

- propose WBS;
- propose dependencies;
- suggest delays;
- draft technical proposals;
- summarize risks;
- generate recommendations.

Humans approve.

## Decision 010 — BIM context layer

BIM may provide:

- spatial context;
- element references;
- issue context;
- model viewer;
- QTO hints;
- location and discipline context.

BIM must not become the execution source of truth.

## Decision 011 — Every new workflow must be auditable

For execution, approvals, baseline changes, delays, claims, and critical document actions, the system must answer:

- who acted;
- what changed;
- when it changed;
- what the old value was;
- what the new value is;
- what object was affected;
- under which tenant/project.

## Decision 012 — PRs must be small

A safe PR changes one domain boundary, not the whole application.

Bad PR:

```text
Refactor tenant isolation across all modules
```

Good PR:

```text
T1.3 Protect RaportActivitate detail/approval routes with tenant guard
```


---

# 02 — Execution Spine

## Canonical spine

```text
Proiect
  -> ProgramReferinta
  -> TaskProgram
  -> RaportActivitate
  -> Pontaj
  -> SituatieLunara
```

This spine is the operational backbone of Edifico.

## Role of each model

### Proiect

The project is the operational container.

It owns or organizes:

- contracts;
- schedules;
- work reports;
- timesheets;
- documents;
- BIM context;
- resources;
- costs;
- delays;
- reports.

Project progress must eventually become execution-based, not only calendar-based.

### ProgramReferinta

The reference program is the contractual or approved planning baseline.

It should eventually support:

- versioning;
- approval;
- baseline selection;
- re-baseline history;
- import provenance;
- relationship to claims and delays.

### TaskProgram

`TaskProgram` is the planned work item.

It should become:

- the operational task;
- the plan-vs-actual comparison unit;
- the delay detection unit;
- the claim impact unit;
- the progress aggregation unit.

Do not create `ExecutionTask` without an ADR.

### RaportActivitate

`RaportActivitate` is executed-work proof.

It should capture:

- who reported;
- which project;
- which planned task, eventually via `task_program_id`;
- what was done;
- quantity;
- percent;
- materials;
- equipment;
- optional BIM context;
- attachments/proof later;
- status and approvals.

### Pontaj

`Pontaj` is time and labor cost truth.

It supports:

- hours worked;
- overtime;
- workforce cost;
- approved labor evidence;
- EVM/cost reports;
- labor productivity analytics later.

### SituatieLunara

`SituatieLunara` is monthly commercial truth.

It should connect:

- executed quantities;
- validated quantities;
- contract/payment status;
- progress claims;
- EVM;
- reporting.

## Current gap

The critical missing link is:

```text
TaskProgram  X  RaportActivitate
```

The system has planned work and actual reports, but the link is not yet operationally enforced.

## Target flow

```text
Approved ProgramReferinta
  -> TaskProgram list
  -> optional crew/worker assignment
  -> RaportActivitate submitted against TaskProgram
  -> approval
  -> TaskProgram actual progress recalculated
  -> delay service checks planned vs actual
  -> dashboard/report/claim uses consistent data
```

## Phased implementation

### Phase ES1 — Tenant-safe access first

Before linking models, make access safe.

### Phase ES2 — Activity service

Move activity workflow into a service.

### Phase ES3 — Add nullable link

Add `RaportActivitate.task_program_id` nullable.

Backfill can come later.

### Phase ES4 — Manual link UI

Allow manager/supervisor to link reports to planned tasks.

### Phase ES5 — Suggested matching

Suggest matching by:

- project;
- WBS;
- date range;
- category;
- description similarity;
- BIM element if available.

### Phase ES6 — Progress aggregator

Approved reports update read-model calculations for `TaskProgram` progress.

### Phase ES7 — Delay engine

Compare planned vs actual at task level.

## Do not do yet

- Do not auto-update contractual baseline without approval.
- Do not allow AI to write progress directly.
- Do not create claims automatically.
- Do not require BIM for task execution.


---

# 03 — Tenant Security Constitution

## Supreme rule

> No cross-tenant data leakage.

Everything else is secondary.

## Current risk profile

The audits found that Edifico has tenant-aware infrastructure but does not yet enforce tenant boundaries uniformly.

Known risks:

- `with_tenant_scope` must be called explicitly;
- many routes use `Model.query.get_or_404(id)`;
- several core legacy models do not have direct `tenant_id`;
- many tenant columns are nullable;
- reports and exports can aggregate globally;
- file storage is shared and ownership checks depend on route validation;
- BIM hierarchy is partly indirectly tenant-owned;
- strict mode is not yet production-safe.

## Tenant modes

### off

Legacy single-tenant behavior.

Rules:

- do not aggressively filter;
- do not break existing deployments;
- acceptable for one company per deployment/database.

### optional

Migration mode.

Rules:

- apply tenant filtering when tenant exists;
- do not assume all legacy rows are safe;
- include global rows only when explicitly allowed.

### strict

SaaS mode.

Rules:

- fail closed;
- no tenant context means no tenant-owned data;
- `tenant_id=NULL` is not customer data unless explicitly declared global;
- ID guessing must not reveal existence;
- batch operations must reject mixed-tenant IDs;
- services must require tenant context.

## Canonical access pattern

```text
route receives id
  -> tenant_access.get_*_or_404(id, tenant_id)
  -> service receives scoped object or tenant-scoped id
  -> service validates tenant again before mutation/export
  -> route renders/sends response
```

## Forbidden pattern

```python
obj = Model.query.get_or_404(id)
```

Forbidden for tenant-owned objects unless explicitly global catalog data.

## Direct vs indirect tenant ownership

### Direct ownership

Model has `tenant_id`.

Examples:

- `Proiect`
- `Contract`
- `ProgramReferinta`
- `TaskProgram`
- many contract/BIM/Gantt models

### Indirect ownership

Model derives tenant through another model.

Examples:

- `RaportActivitate` through `Proiect` / `Angajat`;
- `Pontaj` through `Proiect` / `Angajat`;
- `DocumentProiect` through `Proiect`;
- `ElementBIM` through `Santier` / `ModelBIM` / hierarchy.

For v1, indirect ownership must be implemented through explicit scoped helpers. Do not invent ad-hoc joins in every route.

## Global rows

`tenant_id=NULL` is allowed only for:

- true global catalogs;
- system defaults;
- public configuration templates;
- explicitly reviewed global data.

It is not allowed for customer-owned projects, contracts, activities, timesheets, documents, BIM files, or reports.

## Tenant roadmap

### T1 — Access foundation

- Create canonical tenant access helpers.
- Protect project routes first.

### T2 — Execution/workforce isolation

- Protect `RaportActivitate` and `Pontaj`.
- Add direct `tenant_id` later if needed.

### T3 — Contracts/documents/files

- Scope contract routes.
- Scope financial exports.
- Scope downloads.
- Namespace storage or enforce ownership before every `send_file`.

### T4 — BIM/Gantt hardening

- Scope BIM tree/search/viewer/file APIs.
- Scope BCF/COBie exports.
- Validate Gantt project association.

## Tests required

Every protected route must have two-tenant tests:

- tenant A can access own record;
- tenant A cannot access tenant B record;
- tenant A cannot mutate tenant B record;
- tenant A cannot export tenant B record;
- strict mode fails closed;
- off mode remains legacy compatible.

## Security principle

> UI hiding is not security. Every route and service must enforce access.


---

# 04 — Service Architecture

## Goal

Move Edifico from route-heavy behavior to service-owned business logic.

## Target shape

```text
routes/*
  -> services/security/tenant_access.py
  -> services/projects/project_service.py
  -> services/projects/project_metrics_service.py
  -> services/execution/activity_service.py
  -> services/execution/timesheet_service.py
  -> services/execution/task_progress_service.py
  -> services/contracts/contract_service.py
  -> services/contracts/baseline_service.py
  -> services/contracts/claims_service.py
  -> services/documents/document_service.py
  -> services/planning/gantt_plan_service.py
  -> services/reporting/reporting_service.py
  -> services/bim/bim_service.py
  -> services/bim/bim_issue_service.py
  -> services/bim/bim_import_service.py
```

## Service law

Services are business boundaries.

Routes may:

- authenticate;
- parse request payload;
- call service;
- handle flash/redirect/render/send_file/json.

Routes must not:

- calculate business totals;
- validate domain workflows;
- mutate status directly;
- approve/reject directly;
- generate XLSX/PDF cells;
- query tenant-owned records directly;
- duplicate business rules.

## Phase S1 services

### `services/security/tenant_access.py`

Purpose:

- fail-closed tenant record access;
- project/activity/timesheet/contract/document/BIM scoped getters;
- central place to prevent IDOR.

### `services/execution/activity_service.py`

Purpose:

- create/update `RaportActivitate`;
- submit/approve/reject;
- batch approval;
- delete policy;
- future audit;
- future TaskProgram link.

### `services/execution/timesheet_service.py`

Purpose:

- calculate hours;
- detect day type;
- duplicate validation;
- create/update/submit/approve/reject `Pontaj`;
- support `/teren/pontaj`.

### `services/projects/project_metrics_service.py`

Purpose:

- build project hub DTO;
- project list stats;
- project detail metrics;
- avoid multi-table aggregations in routes.

## Phase S2 services

### `services/projects/project_service.py`

Purpose:

- project create/update/status;
- employee assignment lifecycle;
- site link/unlink;
- project-level policies.

### `services/contracts/baseline_service.py`

Purpose:

- import and version `ProgramReferinta`;
- create/maintain `TaskProgram`;
- baseline approval;
- rebaseline later.

### `services/planning/gantt_plan_service.py`

Purpose:

- safe GanttPlan save/list/open;
- validate project association;
- bridge GanttPlan to ProgramReferinta later.

## Phase S3 services

### `services/contracts/contract_service.py`

Purpose:

- contract CRUD workflows;
- terms;
- offers;
- monthly quantities;
- monthly situations;
- status transitions.

### `services/contracts/claims_service.py`

Purpose:

- claims lifecycle;
- claim-task/term/quantity links;
- future link from Delay Domain.

### `services/documents/document_service.py`

Purpose:

- file upload metadata;
- download authorization;
- revision lifecycle;
- storage namespace.

### BIM services

BIM must be split into:

- `bim_service.py` for hierarchy/viewer/read models;
- `bim_issue_service.py` for issues/comments/BCF;
- `bim_import_service.py` for IFC import/QTO/mapping.

## Phase S4 services

### `services/reporting/reporting_service.py`

Purpose:

- produce DTOs and files;
- never accept unscoped IDs;
- return file descriptors, not Flask responses.

### `services/reporting/dashboard_service.py`

Purpose:

- executive cockpit;
- tenant-safe operational metrics;
- plan vs actual;
- delay and approval metrics.

## Service design rules

1. Services accept `tenant_id` or scoped domain objects.
2. Services should validate tenant again for write/export operations.
3. Services must not depend on templates.
4. Services should return DTOs/results/errors, not Flask responses.
5. Services should be testable with unit/integration tests.
6. Services should not hide database commits unpredictably; transaction behavior must be explicit.
7. Services must preserve PythonAnywhere compatibility.

## Example service result shape

```python
@dataclass
class ServiceResult:
    ok: bool
    value: object | None = None
    error: str | None = None
    code: str | None = None
```

This is optional, but route responses should not need to understand internal implementation details.


---

# 05 — Domain Model and Glossary

## Core domains

### Projects

Primary model: `Proiect`

Responsibilities:

- operational container;
- tenant boundary root;
- project status;
- manager assignment;
- budget and dates;
- link to contract, planning, workforce, documents, BIM.

### Planning / Baseline

Primary models:

- `ProgramReferinta`
- `TaskProgram`
- `GanttPlan`
- `GanttWbsNod`

Rules:

- `GanttPlan` is generated/imported/simulation plan.
- `ProgramReferinta` is contractual/approved reference program.
- `TaskProgram` is the persistent task row.

### Execution

Primary models:

- `RaportActivitate`
- `Pontaj`
- later evidence/proof models.

Rules:

- `RaportActivitate` records work done.
- `Pontaj` records time/cost.
- Approved reports should eventually feed task progress.

### Workforce

Primary models:

- `Angajat`
- `AngajatProiect`
- future `Crew`/`Brigada` model if needed.

Current gap:

- No formal crew/brigade model.
- Project assignment exists but task assignment is missing.

### Contracts and commercial control

Primary models:

- `Contract`
- `OfertaContract`
- `PozitieBoQ`
- `CantitateExecutataLunara`
- `SituatieLunara`
- `Revendicare`

Rules:

- Commercial truth should derive from validated quantities and contractual states.
- Claims should eventually start from delay/impact events.

### BIM context

Primary models:

- `Santier`
- `Cladire`
- `Nivel`
- `Zona`
- `Spatiu`
- `ElementBIM`
- `ModelBIM`
- `IssueBIM`

Rules:

- BIM is optional context.
- BIM must not replace execution truth.
- BIM routes must be tenant-safe before SaaS use.

## Glossary

### Construction Operating System

A system that connects plan, work, people, proof, approvals, delays, costs, and decisions.

### Execution Spine

The canonical chain:

```text
Proiect -> ProgramReferinta -> TaskProgram -> RaportActivitate -> Pontaj -> SituatieLunara
```

### Baseline

An approved reference program used to judge actual execution.

### Rebaseline

A formally approved replacement or revision of baseline, with reason and impact.

### Proof of Work

Evidence that work was executed:

- approved activity report;
- timesheet;
- photo;
- document;
- quantity;
- issue resolution;
- BIM/spatial context;
- supervisor confirmation.

### Delay Event

A first-class operational record of delay, later linked to task, contract, claim, or report.

### Tenant

A company/organization boundary.

### Tenant-owned data

Any data belonging to a company or its projects, contracts, workers, documents, BIM files, reports, or financial records.

### Global data

Truly shared catalogs/configuration. Must be explicitly reviewed. `tenant_id=NULL` does not automatically mean safe global data.

### Context layer

A layer that enriches execution but is not the source of truth.

BIM is a context layer.

## Duplicated concepts to eliminate over time

### Progress

Currently appears in multiple places:

- project progress;
- activity report percent;
- TaskProgram percent;
- BIMTaskSchedule percent;
- SituatieLunara percent.

Target:

- keep local fields where necessary;
- establish clear calculation sources;
- expose one operational progress read-model.

### Approval

Currently duplicated across:

- activities;
- timesheets;
- quantities;
- situations;
- documents;
- BIM workflows.

Target:

- small declarative transition helpers;
- audit events;
- consistent permission model.

### Task

Currently represented by:

- TaskProgram;
- GanttWbsNod/activity snapshot;
- BIMTaskSchedule;
- RaportActivitate description.

Target:

- TaskProgram is operational task;
- other models reference or derive from it.


---

# 06 — Planning and Gantt Strategy

## Role of Gantt

Gantt is a core planning capability, but it is not the final execution backbone.

Current capabilities include:

- F3/Excel/CSV/XML import;
- classification;
- durations;
- WBS generation;
- dependencies;
- validation;
- CPM/critical path;
- S-curve;
- export to MS Project / Primavera / CSV / JSON;
- saved plans.

## Strategic interpretation

Gantt is the engine that can create or analyze candidate plans.

The execution backbone must be persistent and contractual:

```text
GanttPlan candidate
  -> reviewed
  -> promoted/mapped
  -> ProgramReferinta
  -> TaskProgram
```

## Why `GanttPlan` is not the operational task source

`GanttPlan` is currently a saved artifact from pipeline generation/import/export. Its activities may be regenerated and are tied to planning logic.

`TaskProgram` is better suited because it has:

- project relation;
- program relation;
- planned dates;
- actual dates;
- percent;
- predecessors;
- contractual relevance;
- future claim/report linkage.

## Required roadmap

### G1 — Tenant-safe Gantt access

- Validate `proiect_id` when saving GanttPlan.
- Prevent attaching a plan to another tenant's project.
- Scope saved plans in strict mode.

### G2 — Baseline candidate

Allow a GanttPlan to be marked as baseline candidate.

### G3 — Promote to ProgramReferinta

Create a service that converts selected Gantt plan nodes into ProgramReferinta/TaskProgram.

### G4 — Baseline approval

Do not use a baseline operationally until approved.

### G5 — Plan vs actual

Once `RaportActivitate` links to `TaskProgram`, compare:

- planned start/end;
- actual start/end;
- percent planned vs percent actual;
- critical task status;
- delay risk.

### G6 — Rebaseline

Rebaseline must require:

- reason;
- approver;
- old baseline reference;
- new baseline reference;
- impact summary;
- audit.

## Forbidden for now

- Full 4D simulation as core workflow.
- AI-generated baseline without human approval.
- Automatic overwrite of TaskProgram from Gantt without controlled import.
- Long-running plan generation inside web request for huge files.

## Future AI planning

AI may later assist with:

- WBS suggestions;
- dependency suggestions;
- duration assumptions;
- risk flags;
- technical proposal drafts.

But AI planning is only useful when:

- execution reports are linked to TaskProgram;
- delays are first-class;
- historical project data exists;
- tenant-safe data boundaries are enforced.


---

# 07 — BIM Strategy

## Position

BIM is a **context layer**.

It is not the primary product and not the execution source of truth.

## BIM may provide

- spatial location;
- element references;
- model viewing;
- issue context;
- quantity hints;
- discipline context;
- CDE-like document/model version context;
- optional field visualization.

## BIM must not

- block workforce reporting;
- become the only way to create work reports;
- replace TaskProgram;
- replace RaportActivitate;
- replace contract baseline;
- become the focus before tenant security;
- expand into advanced Solibri/Navisworks-like geometry engines now.

## Current BIM risk

The BIM module is broad and contains many subdomains in one route module:

- hierarchy;
- models;
- viewer;
- CDE-ish workflow;
- rules;
- clash;
- IoT;
- 4D/5D;
- realtime;
- BCF;
- COBie;
- API tokens;
- RBAC.

This is powerful but dangerous if not bounded.

## Target BIM boundaries

### `bim_service.py`

- hierarchy read models;
- site/model/element detail DTOs;
- viewer file descriptor;
- BIM context for execution screens.

### `bim_issue_service.py`

- issue lifecycle;
- field issue creation;
- comments;
- BCF import/export scoped by tenant;
- Kanban grouping;
- audit/realtime hooks.

### `bim_import_service.py`

- IFC upload validation;
- model creation;
- import orchestration;
- external mapping;
- QTO extraction.

## BIM + execution integration

Allowed integration points:

```text
RaportActivitate -> optional ElementBIM / Spatiu / Zona
Pontaj -> optional ElementBIM / Spatiu / Zona
IssueBIM -> optional TaskProgram/RaportActivitate later
TaskProgram -> optional BIM context later
```

Do not make BIM mandatory.

## BIM tenant safety

BIM must be treated as high sensitivity.

- Model files can reveal full building geometry.
- BCF exports can reveal issues, responsibilities, and project status.
- Search/tree APIs can leak project existence and scale.

Every BIM file/export/detail route must be tenant-scoped before multi-company SaaS use.

## Deferred features

Do not expand now:

- advanced Digital Twin;
- IoT analytics;
- advanced clash detection;
- COBie as core sales feature;
- public API expansion;
- APS enterprise workflow;
- complex real-time collaboration.

These may return after the execution spine is stable.


---

# 08 — Roadmap

## Strategic order

```text
Security foundation
  -> service boundaries
  -> execution spine link
  -> progress and delay
  -> proof of work
  -> reporting/cockpit
  -> AI and advanced automation
```

## Track A — Tenant Security

### T1.1 Tenant Access Foundation

- Create canonical tenant access helpers.
- Preserve mode off behavior.
- Add tests.
- Pilot on one project route.

### T1.2 Project Tenant Guard Expansion

- Protect project list/detail/hub/edit/status/export.
- Assign tenant on project creation.
- Add cross-tenant tests.

### T1.3 Activity Tenant Guard

- Protect RaportActivitate routes and lists.
- Preserve workflow.
- No service extraction yet.

### T1.4 Timesheet Tenant Guard

- Protect Pontaj routes and exports.
- Preserve workflow.

### T1.5 Contract Tenant Guard

- Protect Contract, ProgramReferinta, TaskProgram, SituatieLunara, Revendicare.

### T1.6 Document/File Tenant Guard

- Protect Document and DocumentProiect downloads/previews/exports.

### T1.7 BIM/Gantt Tenant Hardening

- Protect BIM file/tree/search/export routes.
- Validate Gantt project association.

## Track B — Service Architecture

### S1.1 Activity Service

- Extract create/update/submit/approve/reject for RaportActivitate.

### S1.2 Timesheet Service

- Extract hour calculation, create/update/submit/approve/reject for Pontaj.

### S1.3 Project Metrics Service

- Extract hub/list/detail metrics.

### S2.1 Baseline Service

- Extract ProgramReferinta/TaskProgram import/versioning.

### S2.2 Gantt Plan Service

- Safe GanttPlan operations.

### S3.1 Contract Service

- Contract and monthly situation workflows.

### S3.2 Document Service

- Upload/download/revision authorization.

### S3.3 BIM Issue Service

- Field issues and BIM issue workflow.

### S4.1 Reporting Service

- Export/report DTOs and file generation.

## Track C — Product Spine

### P1.1 Link RaportActivitate to TaskProgram

- Add nullable `task_program_id`.
- Manual linking.
- Tests.

### P1.2 Task Progress Service

- Approved reports aggregate into task progress read model.

### P1.3 Baseline Approval

- Operationalize `ProgramReferinta.aprobat`.

### P1.4 Plan vs Actual

- Task-level planned vs actual reporting.

## Track D — Operational Intelligence

### D1.1 Delay Domain MVP

- First-class delay model.
- Link to project/task/term/report.

### D1.2 Delay Detection

- Read-only detection from planned vs actual.

### D1.3 Delay Approval

- Confirm/approve/reject/close delay.

### D1.4 Claims Link

- Delay -> Revendicare.

## Track E — Proof of Work

### W1.1 Activity Attachments

- Photos/files on RaportActivitate.

### W1.2 Supervisor confirmation

- Separate field-level confirmation from manager approval.

### W1.3 Immutable monthly closure

- Lock snapshot after emission.

## Track F — Executive Cockpit

### R1.1 Cockpit read model

- Project risk;
- delays;
- approvals pending;
- plan vs actual;
- cost indicators;
- missing reports.

### R1.2 Dashboard UI

- Lightweight server-rendered dashboard.

## Track G — AI Later

Only after Tracks A-F have mature data.

AI initiatives:

- Gantt suggestions;
- technical proposal drafts;
- delay narrative drafting;
- claim evidence summaries;
- productivity insights.

## What not to prioritize

- advanced BIM;
- Digital Twin;
- IoT expansion;
- microservices;
- SPA rewrite;
- Celery/Redis dependency;
- AI replacing human approval.


---

# Appendix — Tenant Access Foundation and T1.2 Project Route Integration

This appendix imports the implementation documentation produced after T1.1/T1.2.

Source file in this package:

```text
docs/architecture/tenant_access_foundation.md
```

## Summary

The tenant access foundation introduces `services/security/tenant_access.py` as the opt-in boundary for tenant-safe query and lookup behavior. It does not apply global SQLAlchemy filters automatically and does not change routes that do not use it.

The layer supports three modes:

- `off`: legacy single-tenant compatibility; unfiltered behavior is preserved.
- `optional`: tenant filtering applies when a tenant exists; global `NULL` rows require explicit `include_global=True`.
- `strict`: fail-closed for normal users without tenant; direct-tenant models return only current tenant rows; `NULL` rows are excluded unless explicitly allowed.

## Available primitives

- `get_current_tenant_id_safe()`
- `get_tenant_mode()`
- `is_super_admin(user)`
- `model_has_tenant_id(model)`
- `query_for_tenant(model, tenant_id=None, include_global=False)`
- `get_or_404_for_tenant(model, object_id, tenant_id=None, include_global=False)`
- `ensure_same_tenant(obj, tenant_id=None, include_global=False)`
- `require_same_tenant(obj, tenant_id=None, include_global=False)`
- `get_project_or_404(project_id, tenant_id=None)`
- `tenant_id_for_new_record_or_403()`

## T1.2 Project Route Integration

Protected project routes:

| Route | Change |
|---|---|
| `proiecte.lista` | Uses `query_for_tenant(Proiect)` for listing and statistics. |
| `proiecte.adauga` | Assigns `tenant_id` on new project creation in optional/strict when current tenant exists. |
| `proiecte.detalii` | Uses `get_project_or_404(id)`. |
| `proiecte.hub` | Uses `get_project_or_404(id)`. |
| `proiecte.editeaza` | Uses `get_project_or_404(id)`. |
| `proiecte.schimba_status` | Uses `get_project_or_404(id)` before mutation. |
| `proiecte.export_excel` | Uses `get_project_or_404(id)` before export generation. |

## Remaining risks after T1.2

The following remain deferred and must not be assumed protected:

- `AngajatProiect` project assignments;
- legacy project `Document` records;
- resource and vehicle data;
- project BIM links;
- EVM, project reports, and nested aggregates;
- contracts/Gantt/BIM/document data read inside project hub;
- manager dropdowns and form choices;
- exports and reports aggregating models without direct `tenant_id`.

## Next integration

T1.3 must protect `RaportActivitate` through an indirect ownership helper using the real ownership path through `Proiect` and `Angajat`, without schema changes and without service extraction.
