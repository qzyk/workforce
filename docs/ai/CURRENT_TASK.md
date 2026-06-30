# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
T1.5C Contract Form/Input Tenant Guard Hardening
```

This is a narrow tenant/input hardening task. It is NOT Contract Service
extraction and it is NOT Commercial / SituatieLunara Service extraction.

IMPORTANT: Contract / Commercial service extraction is NOT authorized until the
P1 tenant/input issue found by the Contract / Commercial no-code gate is fixed
and reviewed by Albert.

Current canonical base commit:

```text
4c15b01 S1.4A project details context extraction
```

Latest coordination state after this docs update:

```text
Contract / Commercial Service No-Code Gate — COMPLETED.
Service extraction blocked by P1 contract form/input tenant issue.
Next authorized task: T1.5C Contract Form/Input Tenant Guard Hardening.
```

Current canonical branch:

```text
feat/s1.4a-project-details-context-extraction
```

---

## Previous completed gate — COMPLETED / NOT APPROVED FOR EXTRACTION

```text
Contract / Commercial Service No-Code Understanding / Collision Safety Gate
```

Verdict:

```text
P0: none
P1: present
Contract / Commercial service extraction is NOT approved yet.
```

Gate findings:

```text
- routes/contracte.py has broad route-level tenant safety through T1.5 helpers.
- no broad raw-query direct-access pattern was found in routes/contracte.py.
- commercial/reporting services remain legacy functional services, not approved
  direct tenant-safe boundaries.
- Contract core, Commercial/Situatie, Oferta/BoQ, Claims, PV/export/reporting
  extraction must remain deferred.
```

P1 blocker:

```text
TermenContractForm.responsabil_id is populated from raw Utilizator.query with
all active users, and termen_nou / termen_editeaza can save responsabil_id
without same-tenant validation.
```

Gate validation:

```text
py_compile routes/contracte.py services/situatii.py services/evm.py
services/rapoarte_lucrari.py: OK
contract/commercial suite: 139 passed
project regression: 67 passed
activity/timesheet regression: 150 passed
Flask smoke equivalent: ok 365 routes
```

---

## Current task goal

T1.5C must fix the P1 contract form/input tenant issue only:

```text
1. Fix TermenContractForm.responsabil_id tenant leakage.
2. Make responsabil_id choices tenant-safe.
3. Validate responsabil_id belongs to the current tenant before saving in
   termen_nou and termen_editeaza.
4. Preserve existing form behavior and route behavior.
5. Do not change schema.
6. Do not change templates.
7. Do not extract services.
```

Targeted tests should cover:

```text
- responsible dropdown tenant scoping
- foreign responsible user rejected
- create/edit term behavior preserved
- strict/optional/off mode behavior where applicable
```

---

## Initial scope for T1.5C

Allowed files for implementation, if Albert explicitly approves T1.5C:

```text
forms/contract_forms.py
routes/contracte.py only where necessary for termen_nou / termen_editeaza
targeted tests only
docs/ai only after implementation validation
```

---

## No-touch boundaries for T1.5C

```text
- no services/contract_service.py
- no services/situatii.py
- no commercial/reporting service changes
- no Project service changes
- no Project hub changes
- no Gantt/BIM/Activity/Timesheet changes
- no models
- no migrations
- no templates/frontend/static
- no route URL changes
- no Contract / Commercial service extraction
```

---

## Do not start

Do not start Contract Service extraction. Do not start Commercial /
SituatieLunara extraction. Do not create `services/contract_service.py`. Do not
modify commercial/reporting services. The current authorized task is only the
narrow T1.5C tenant/input hardening fix, and implementation still requires
Albert's explicit next prompt.
