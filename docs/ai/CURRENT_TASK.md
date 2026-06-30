# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.4 Project Details / Cross-Domain Context No-Code Gate
```

This is a READ-ONLY gate. It produces a no-code understanding / collision-safety
report only.

IMPORTANT: S1.4 IMPLEMENTATION IS NOT AUTHORIZED.
Project detalii/hub extraction may start only after this no-code gate is reviewed
and approved by Albert.

Current canonical base commit:

```text
a9fabfc S1.3B project create edit status extraction
```

Current canonical branch:

```text
feat/s1.3b-project-create-edit-status-extraction
```

---

## Previous completed review (S1.C3) — APPROVED

```text
S1.C3 Project Service Extraction Review — APPROVED (no P0/P1 blockers)
```

Verdict: S1.3 Project Service Extraction is APPROVED for the S1.3A/S1.3B boundary
(see DECISIONS_LOG D017).

S1.C3 recorded outcome:

```text
- services/project_service.py is a coherent, HTTP-free Project service for
  read/list context, financial data assembly, and create/edit/status save
- routes/proiecte.py keeps decorators, request args/form/json, ProiectForm +
  validate_on_submit, _populeaza_manageri_form, auto cod_proiect GET pre-fill,
  editeaza GET locatie split, render/flash/redirect/jsonify, invalid-status 400
- tenant safety preserved; no new raw tenant-owned queries in the service
- pre-existing route/form global queries preserved (auto-code Proiect.query;
  form validate_cod_proiect Proiect.query; form __init__ Utilizator.query
  overridden by _populeaza_manageri_form)
- service-commit / route-rollback consistent; read-only helpers read-only;
  mutators commit once; route rollback wrappers present
- tests sufficient
```

S1.C3 review re-ran (read-only, no code changes):

```text
py_compile OK
project targeted suite: 69 passed
regression safety (activity + timesheet + timesheet routes): 150 passed
Flask smoke: ok 27 proiecte routes
Last full suite (at S1.3B): 1167 passed, 39 skipped, 4 warnings
```

P2/P3 (cleanup NOT authorized): detalii/hub/nested/report route-resident deferrals;
auto-code + editeaza GET locatie split direct-test gaps; pre-existing route/form
global queries preserved; docs/audits absent; CLAUDE.md stale.

---

## Goal of the current gate (S1.4 no-code)

Prove understanding of the Project detalii + hub cross-domain context BEFORE any code:

```text
1. Understand current detalii behavior.
2. Understand current hub behavior.
3. Map cross-domain dependencies:
   - timesheet / Pontaj
   - activity / RaportActivitate
   - contract / OfertaContract / Contract
   - commercial / SituatieLunara / CantitateExecutata
   - GanttPlan / GanttWbsNod
   - BIM / ModelBIM / Cladire / ElementBIM
   - documents
   - HR assignments (AngajatProiect)
   - EVM / reports (services.evm)
4. Identify which parts are Project-owned context (candidate for project_service).
5. Identify which parts must remain route-owned (render/HTTP).
6. Identify which parts should remain delegated to existing services (evm/situatii/etc.).
7. Identify collision risk with Contract / Commercial / Gantt / BIM domains.
8. Decide whether detalii and hub should be split into separate future slices.
9. Produce a no-code report only. Do not implement.
```

---

## Initial scope for the S1.4 gate

```text
- Project detalii/hub cross-domain context only
- no Contract Service implementation
- no Commercial / SituatieLunara implementation
- no Gantt Service implementation
- no BIM Service implementation
- no schema changes
- no migrations
- no templates / static / frontend changes
- no activity / timesheet changes
- no nested-resource implementation
- no report / export implementation
```

Follow the S1.x service-extraction constraints (D014 + D015 + D016 + D017):
gate-first; extract one domain's behavior only; no schema changes; preserve
tenant guards and route behavior; HTTP-free services; service-commit /
route-rollback for any future mutating slice; reuse the existing
services/project_service.py for Project-owned context (do not create another
project file); a Project context aggregator that reaches into other domains must
keep using those domains' existing tenant-safe query helpers / services.

---

## No-touch boundaries for the S1.4 gate

```text
- do not modify code, tests, routes, services, forms
- do not modify models / migrations / templates / static / frontend
- do not start S1.4 implementation
- do not start detalii / hub extraction
- do not start Contract / Commercial / Gantt / BIM extraction
- do not touch Activity / Timesheet services
- do not alter the approved S1.3A / S1.3B project boundary
```

---

## Do not start

Do not start any implementation. The current authorized task is ONLY the S1.4
Project detalii/hub cross-domain no-code understanding / collision-safety gate
(report only). Any follow-up implementation requires a separate explicit approval
from Albert.
