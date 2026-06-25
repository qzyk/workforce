# ADR-0002 — Execution Spine

## Status

Accepted.

## Decision

The execution spine is:

```text
Proiect -> ProgramReferinta -> TaskProgram -> RaportActivitate -> Pontaj -> SituatieLunara
```

## Rationale

`TaskProgram` is already the best candidate for operational task because it is persistent, project-linked, program-linked, date-aware, and contractually relevant.

`RaportActivitate` records executed work.

`Pontaj` records time/cost.

`SituatieLunara` records commercial monthly truth.

## Consequences

- Do not create `ExecutionTask` now.
- Link `RaportActivitate` to `TaskProgram` later.
- Build progress/delay/dashboard on this chain.
