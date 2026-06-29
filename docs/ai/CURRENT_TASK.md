# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
T1.C14 Final Tenant Guard Review
```

Note: T1.14 Activity BIM Context Tenant Guard was completed.
Commit: 818c90d T1.14 activity BIM context tenant guard
Branch: feat/t1.14-activity-bim-context-tenant-guard

Current canonical base commit:

```text
818c90d T1.14 activity BIM context tenant guard
```

Expected branch name:

```text
feat/t1.c14-final-tenant-guard-review
```

---

## Goal

Final adversarial review of the full T1.x tenant guard stack (T1.1–T1.14) before approving S1.1.

Read-only review. No new implementation unless a CRITIC/MAJOR finding requires a fix.

Review lenses:
1. Coverage: all route-level raw queries protected?
2. Consistency: all modules use `services/security/tenant_access.py` helpers?
3. Mode integrity: `MULTI_TENANT_MODE=off` preserves legacy behavior?
4. Fail-closed: `strict` mode fails correctly for users without tenant?
5. Foreign ID leak: foreign tenant IDs return 404?
6. Super-admin scope: global access explicit and not leaking?
7. Activity BIM context (T1.14): dropdowns, filters, and aggregates all scoped?

If T1.C14 verdict is APPROVED, next task is S1.1 Activity Service Extraction.

---

## Previous task (T1.14) — completed

T1.14 Goal was:

---

## Blocker found by T1.C13

T1.C13 found:

```text
routes/activitati.py still exposes raw BIM context IDs/dropdowns.
routes/bim.py still aggregates RaportActivitate and Pontaj by raw element_bim_id.
```

Known risky patterns:

```text
Santier.query
Cladire.query
Nivel.query
Zona.query
Spatiu.query.get()
ElementBIM.query
RaportActivitate.query.filter_by(element_bim_id=...)
Pontaj.query.filter_by(element_bim_id=...)
```

---

## Files expected to change

Allowed files for T1.14 should be limited to:

```text
services/security/tenant_access.py
routes/activitati.py
routes/bim.py
tests/unit/test_tenant_access_activity_bim_context.py
tests/integration/test_tenant_access_activity_bim_context_routes.py
docs/architecture/tenant_access_foundation.md
```

Do not touch unrelated domains.

---

## Required behavior

`MULTI_TENANT_MODE=off`:

```text
Preserve legacy behavior.
```

`MULTI_TENANT_MODE=optional`:

```text
Tenant users see only same-tenant BIM context options.
Foreign BIM IDs are rejected before mutation.
No-tenant users remain migration-friendly where foundation rules allow.
```

`MULTI_TENANT_MODE=strict`:

```text
Normal users without tenant fail closed.
Foreign BIM context IDs return 404.
Super-admin without tenant remains explicit/global where existing foundation allows.
```

---

## Required tests

Add deterministic two-tenant tests for:

1. Activity dropdown/filter scoping.
2. Activity create/edit blocking foreign `element_bim_id`.
3. Activity create/edit blocking foreign `spatiu_id`.
4. Mixed tenant BIM context rejection.
5. Derived zone from `Spatiu` using tenant-safe lookup.
6. BIM element detail excluding foreign contaminated `RaportActivitate`.
7. BIM element detail excluding foreign contaminated `Pontaj`.
8. API activity/count endpoint excluding foreign rows.

---

## Required commands

Use:

```bash
PY=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
```

Run syntax checks:

```bash
$PY -m py_compile \
  services/security/tenant_access.py \
  routes/activitati.py \
  routes/bim.py \
  tests/unit/test_tenant_access_activity_bim_context.py \
  tests/integration/test_tenant_access_activity_bim_context_routes.py
```

Run targeted tests:

```bash
$PY -m pytest \
  tests/unit/test_tenant_access_activity_bim_context.py \
  tests/integration/test_tenant_access_activity_bim_context_routes.py -q
```

Run full tenant suite:

```bash
$PY -m pytest tests/unit/test_tenant_access*.py tests/integration/test_tenant_access_*_routes.py -q
```

Run existing activity/BIM regressions if present:

```bash
$PY -m pytest \
  tests/unit/test_activitati*.py \
  tests/integration/test_activitati*.py \
  tests/unit/test_bim*.py \
  tests/integration/test_bim*.py -q
```

Run:

```bash
git diff --check
```

---

## Commit rule

If tests pass and only allowed files changed:

```bash
git commit -m "T1.14 activity BIM context tenant guard"
```

---

## Do not start

Do not start:

```text
S1.1 Activity Service Extraction
S1.2 Timesheet Service Extraction
T1.7B BIM Service Boundary Hardening
T1.9B Reporting Service Boundary Hardening
```

This task is only T1.14.
