# CLAUDE.md — Edifico / Workforce Canonical AI Knowledge

This file is the mandatory operating context for Claude Code inside the `qzyk/workforce` repository.

Claude Code must treat this file, together with `docs/ai/PROJECT_STATE.md`, `docs/ai/DECISIONS_LOG.md`, `docs/ai/CURRENT_TASK.md`, and `docs/ai/DO_NOT_TOUCH.md`, as the source of truth.

If Claude's memory, an old chat, an old worktree, or a previous branch conflicts with these files, these files win.

---

## 1. Product identity

Repository:

```text
qzyk/workforce
```

Product:

```text
Edifico / EDIFICO WORKFORCE
```

Product direction:

```text
Construction Operating System / construction execution layer
```

This is not a BIM clone, not a Solibri clone, and not a pure planning tool.

BIM is a context layer only.

---

## 2. Canonical Execution Spine

The execution spine is:

```text
Company / Tenant
→ Project
→ ProgramReferinta
→ TaskProgram
→ RaportActivitate
→ Pontaj
→ SituatieLunara
```

More explicitly:

```text
Proiect
→ ProgramReferinta aprobat
→ TaskProgram
→ RaportActivitate + Pontaj + proof attachments
→ aprobare
→ progress
→ delays / claims / monthly situations / dashboards
```

Core meanings:

- `TaskProgram` becomes the operational task after plan/baseline promotion.
- `RaportActivitate` is proof of executed work.
- `Pontaj` is labor/time/cost truth.
- `SituatieLunara` is the monthly contractual/commercial closing surface.
- BIM is context, not the source of truth.
- Gantt planning/simulation can exist, but operational/contractual plan is promoted to `ProgramReferinta` / `TaskProgram`.

---

## 3. Architecture rules

Current architecture:

- Flask
- SQLAlchemy
- Alembic
- server-rendered templates
- modular monolith
- PythonAnywhere deployment
- no microservices
- no frontend rewrite
- no Celery/Redis unless explicitly approved later
- no new `ExecutionTask` model now

Claude must not introduce a new architecture unless the current task explicitly says so.

---

## 4. Tenant guard status

Canonical tenant guard stack completed:

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
```

Latest canonical completed commit:

```text
fe25b6c T1.13 locations audit api tokens tenant guard
```

Latest checkpoint:

```text
T1.C13 Final Tenant Guard Review
```

T1.C13 result:

```text
Tenant guard phase is mostly complete, but one more tenant guard PR is needed first.
```

Current blocker before service extraction:

```text
T1.14 Activity BIM Context Tenant Guard
```

Do not start `S1.1 Activity Service Extraction` before T1.14 and T1.C14 are completed cleanly.

---

## 5. Current known blocker

T1.C13 found remaining Activity BIM context tenant gaps:

- `routes/activitati.py` still exposes raw BIM context IDs/dropdowns.
- Activity filters/forms still use raw BIM context access around:
  - `element_bim_id`
  - `santier_id`
  - `cladire_id`
  - `nivel_id`
  - `zona_id`
  - `spatiu_id`
- `routes/bim.py` still aggregates `RaportActivitate` and `Pontaj` by raw `element_bim_id` on BIM element detail/count paths.

This must be closed before service extraction.

---

## 6. Claude Code operating protocol

Before any coding task, Claude must read:

```text
CLAUDE.md
docs/ai/PROJECT_STATE.md
docs/ai/DECISIONS_LOG.md
docs/ai/CURRENT_TASK.md
docs/ai/DO_NOT_TOUCH.md
docs/architecture/tenant_access_foundation.md
```

Then run:

```bash
git status
git branch --show-current
git log --oneline -30
git worktree list
```

Claude must stop if the canonical worktree is dirty.

Claude must not use external Claude experimental worktrees as source material.

External Claude worktrees under:

```text
/Users/albertciolacu/workforce/.claude/worktrees/
```

are non-authoritative experimental worktrees.

Claude must not:

- merge them;
- delete them;
- clean them;
- copy code from them;
- use them to override the canonical branch.

---

## 7. Canonical worktree

Use only:

```text
/Users/albertciolacu/workforce-t1.5-contract
```

Do not work in:

```text
/Users/albertciolacu/workforce
```

The `/Users/albertciolacu/workforce` tree has unrelated/experimental work and Claude worktrees.

---

## 8. General implementation rules

Unless the task explicitly allows it, Claude must not:

- change schema;
- add migrations;
- add tenant_id columns;
- create new service files;
- start service extraction;
- refactor workflows;
- change approval statuses;
- change export formats;
- move uploaded/generated files;
- touch unrelated domains;
- commit unrelated files.

For tenant/security tasks:

- preserve `MULTI_TENANT_MODE=off`;
- in `optional`, tenant users must be scoped;
- in `strict`, normal users without tenant must fail closed;
- foreign IDs should usually return 404, not leak existence;
- super-admin without tenant remains explicit/global only where intended;
- use `services/security/tenant_access.py` helpers;
- do not duplicate tenant filtering logic unless helper coverage does not exist.

---

## 9. Allowed roadmap sequence from current state

Current required next step:

```text
T1.14 Activity BIM Context Tenant Guard
```

Then:

```text
T1.C14 Final Tenant Guard Review
```

Only if T1.C14 is clean:

```text
S1.1 Activity Service Extraction
```

Do not skip these steps.

---

## 10. Reporting format

Every implementation task must end with a completion report including:

1. Branch/worktree used.
2. Base commit.
3. Files changed.
4. Helpers added or reused.
5. Route/service areas protected or changed.
6. Behavior by tenant mode.
7. Tests added.
8. Tests run.
9. Known limitations.
10. Remaining risks.
11. Commit hash if committed.
12. Final verdict.

If any test fails, report exactly and do not hide it.
