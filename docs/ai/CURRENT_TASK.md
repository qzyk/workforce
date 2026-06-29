# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.1 Activity Service Extraction
```

Note: T1.C14 Final Tenant Guard Review APPROVED.
Fix commit: 7329cd7 T1.C14 fix: raport_lunar pontaje tenant-safe
246 tenant tests passed.

T1.C14 finding fixed:
  routes/activitati.py:1116 — Pontaj.query raw in raport_lunar()
  replaced with query_timesheets_for_tenant()

Current canonical base commit:

```text
7329cd7 T1.C14 fix: raport_lunar pontaje tenant-safe
```

Expected branch name for S1.1:

```text
feat/s1.1-activity-service-extraction
```

---

## T1.C14 — APPROVED

All 7 review lenses passed. Tenant guard stack T1.1–T1.14 is clean.

One MAJOR finding was fixed:
- `routes/activitati.py raport_lunar()` leaked cross-tenant Pontaj in Excel export.
- Fixed by replacing raw `Pontaj.query.filter` with `query_timesheets_for_tenant()`.

Accepted limitations (pre-existing, out of T1.x scope):
- Pontaj without direct tenant_id — owned through Proiect/Angajat, indirect scoping correct.
- AngajatProiect — scoped via proiect/angajat validated objects.
- BIMComment — owned through validated issue.
- Services not yet independent security boundaries — route-validated only.

---

## S1.1 Goal

Extract activity behavior into a dedicated service without schema changes.

Per D014 constraints:
- Extract activity behavior only.
- Avoid schema changes.
- Preserve workflows and statuses.
- Keep MULTI_TENANT_MODE=off compatible.
- Fail closed in strict mode.
- Use tenant_access.py helpers.
- Avoid raw RaportActivitate, Pontaj, Proiect, Angajat, or BIM context lookups.
- Add direct service-level tests.

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
