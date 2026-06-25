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
