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
