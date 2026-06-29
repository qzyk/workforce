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
