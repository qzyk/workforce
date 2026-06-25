# Codex Playbook — Edifico

## Role

Codex is an implementation agent.

Codex should:

- inspect code;
- make small changes;
- write tests;
- update docs;
- preserve existing behavior;
- create focused PRs.

Codex should not:

- make product strategy decisions;
- rewrite the app;
- change stack;
- add microservices;
- invent new domain models without ADR;
- bypass tenant checks;
- implement broad features without a prompt.

## Required context for every Codex session

Before coding, Codex must read:

```text
docs/constitution/00_vision.md
docs/constitution/01_non_negotiable_decisions.md
docs/constitution/02_execution_spine.md
docs/constitution/03_tenant_security.md
docs/constitution/04_service_architecture.md
docs/constitution/08_roadmap.md
```

If relevant, read:

```text
docs/audits/phase_0_repository_audit.md
docs/audits/phase_0_execution_domain_audit.md
docs/audits/phase_0_tenant_risk_audit.md
docs/audits/phase_0_service_extraction_plan.md
```

## Absolute rules

1. Do not rewrite.
2. Do not change Flask/SQLAlchemy/Alembic/PythonAnywhere.
3. Do not add microservices.
4. Do not add Celery/Redis requirements.
5. Do not introduce `ExecutionTask`.
6. Do not make BIM mandatory.
7. Do not implement AI unless explicitly requested.
8. Do not change broad behavior in security/refactor PRs.
9. Do not use `Model.query.get_or_404(id)` for tenant-owned data.
10. Do not export/download tenant-owned files without scoped access.

## PR size rule

A Codex PR should usually touch:

- one domain;
- one route file or one service boundary;
- one test group;
- one documentation file.

If a PR touches more than five major modules, Codex must stop and ask for review.

## Implementation pattern

Every implementation prompt should include:

- scope;
- files allowed;
- files not allowed;
- behavior that must remain unchanged;
- test requirements;
- documentation requirements;
- expected output summary.

## Testing rules

Codex must run targeted tests.

If full suite is too large, Codex must state:

- which tests were run;
- which tests were not run;
- why;
- risk of not running them.

## Documentation rules

Every architectural PR updates one of:

- `docs/constitution/*`
- `docs/architecture/*`
- `docs/adr/*`
- `docs/checklists/*`

## Tenant work rules

When doing tenant work:

- preserve `MULTI_TENANT_MODE=off` behavior;
- fail closed in strict mode;
- add two-tenant tests;
- do not include `tenant_id=NULL` customer rows by default;
- avoid partial batch processing;
- log or document denied cases.

## Service extraction rules

When extracting services:

- first copy behavior behind tests;
- keep route response identical;
- do not change templates unless needed;
- avoid changing DB schema;
- preserve existing flash/redirect flows;
- create DTOs where helpful.

## Good prompt examples

```text
Implement T1.3 Activity Tenant Guard.
Only protect activity routes.
No service extraction.
No schema changes.
Preserve off mode.
Add strict-mode IDOR tests.
```

```text
Extract timesheet hour calculation into timesheet_service.py.
No route behavior changes.
Add unit tests for overtime/day type.
```

## Bad prompt examples

```text
Fix tenant isolation everywhere.
```

```text
Refactor Edifico architecture.
```

```text
Add AI planning and dashboard.
```

## Codex final response template

Every Codex task should finish with:

```text
Files changed:
Behavior changed:
Tests added:
Tests run:
Known limitations:
Recommended next PR:
```
