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
