# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
Contract / Commercial Service No-Code Understanding / Collision Safety Gate
```

This is a READ-ONLY gate. It produces a no-code understanding / collision-safety
report only.

IMPORTANT: Contract / Commercial implementation is NOT authorized.
Contract / Commercial extraction may start only after this no-code gate is
reviewed and approved by Albert.

Current canonical base commit:

```text
4c15b01 S1.4A project details context extraction
```

Latest coordination state after the previous gate:

```text
S1.5 Project Hub / Cross-Domain Aggregator No-Code Gate — COMPLETED
Decision: keep hub route-resident.
```

Current canonical branch:

```text
feat/s1.4a-project-details-context-extraction
```

---

## Previous completed gate (S1.5) — COMPLETED

```text
S1.5 Project Hub / Cross-Domain Aggregator No-Code Gate
```

Verdict: COMPLETED. hub remains route-resident. S1.5 implementation should NOT
be prepared.

S1.5 recorded outcome:

```text
- no P0 blockers
- no P1 blockers
- hub is read-only and tenant-guarded
- hub uses tenant-safe query helpers
- hub has no raw-query risk
- hub mutates nothing
- hub commits nothing
- _safe fails closed to default/empty values
- hub is a cross-domain navigation/presentation aggregator
- hub is not Project-owned enough to move into services/project_service.py
- services/project_service.py must not absorb hub
- a separate cross-domain aggregator service is premature
- Project service extraction line is effectively complete for Project-owned surfaces
```

S1.5 gate validation:

```text
py_compile routes/proiecte.py services/project_service.py: OK
project targeted suite: 80 passed
cross-domain regression suite: 150 passed
Flask smoke: ok 27 proiecte.* routes
Last full suite from S1.4A: 1178 passed, 39 skipped, 4 warnings
```

---

## Current gate goal

Prove understanding of the safe Contract / Commercial service boundary BEFORE
any code:

```text
1. Understand current routes/contracte.py behavior.
2. Understand existing tenant guards from T1.5.
3. Understand contract create/edit/status/list/details behavior.
4. Understand OfertaContract behavior.
5. Understand Contract behavior.
6. Understand Deviz / CantitateExecutata / SituatieLunara / monthly closing
   interactions if present.
7. Understand existing services/situatii.py.
8. Understand existing services/evm.py interactions if relevant.
9. Understand whether services/rapoarte_lucrari.py is commercial/reporting and
   how it overlaps.
10. Identify what is Contract-owned.
11. Identify what is Commercial/SituatieLunara-owned.
12. Identify what must remain route-owned.
13. Identify collision risk with Project, Gantt, Activity, Timesheet, BIM, and
    reporting.
14. Decide the safest service boundary and split.
15. Produce a no-code report only. Do not implement.
```

---

## Initial scope for the current gate

```text
- Contract / Commercial understanding only
- no implementation
- no Project service changes
- no hub changes
- no Gantt implementation
- no BIM implementation
- no Activity / Timesheet changes
- no schema changes
- no migrations
- no templates / frontend changes
- no route URL changes
```

---

## No-touch boundaries for the current gate

```text
- do not modify code, tests, routes, services, forms
- do not modify models / migrations / templates / static / frontend
- do not start Contract Service extraction
- do not start Commercial / SituatieLunara extraction
- do not start Gantt Service extraction
- do not start hub extraction
- do not start broad Project Service extraction
- do not touch Activity or Timesheet services
```

---

## Do not start

Do not start any implementation. The current authorized task is ONLY the
Contract / Commercial Service no-code understanding / collision-safety gate
(report only). Any follow-up implementation requires a separate explicit
approval from Albert.
