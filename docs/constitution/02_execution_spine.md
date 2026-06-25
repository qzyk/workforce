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
