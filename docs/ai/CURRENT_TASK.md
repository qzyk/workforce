# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.5 Project Hub / Cross-Domain Aggregator No-Code Gate
```

This is a READ-ONLY gate. It produces a no-code understanding / collision-safety
report only.

IMPORTANT: S1.5 IMPLEMENTATION IS NOT AUTHORIZED.
hub extraction or aggregator implementation may start only after this no-code gate
is reviewed and approved by Albert.

Current canonical base commit:

```text
4c15b01 S1.4A project details context extraction
```

Current canonical branch:

```text
feat/s1.4a-project-details-context-extraction
```

---

## Previous completed review (S1.C4) — APPROVED

```text
S1.C4 Project Details Context Extraction Review — APPROVED (no P0/P1 blockers)
```

Verdict: S1.4A Project Details Context Extraction is APPROVED (see DECISIONS_LOG D018).

S1.C4 recorded outcome:

```text
- get_project_detail_context() is the approved Project details context helper
  (read-only, HTTP-free, additive; S1.3A/S1.3B helper bodies unchanged)
- detalii route keeps get_project_or_404(id), request.args (luna/anul),
  render_template('proiecte/detalii.html', ...), HTTP behavior
- hub byte-identical to BASE (untouched, deferred)
- ore_per_angajat aggregate accepted (tenant-scoped via query_timesheets_for_tenant subquery)
- no raw Proiect/Pontaj/Angajat/RaportActivitate/Document.query in the service
- P3: route financial wrappers (_get_total_ore etc.) now dead code; removal NOT authorized
```

S1.C4 review re-ran (read-only, no code changes):

```text
py_compile OK
project targeted suite: 80 passed
cross-domain regression (timesheet routes + activity + timesheet service): 150 passed
Flask smoke: ok 27 proiecte routes
Last full suite (at S1.4A): 1178 passed, 39 skipped, 4 warnings
```

---

## Goal of the current gate (S1.5 no-code)

Prove understanding of the Project `hub` cross-domain aggregator BEFORE any code:

```text
1. Understand current hub behavior.
2. Verify hub is a cross-domain aggregator.
3. Map current hub dependencies:
   - Contract / Contracte
   - OfertaContract
   - SituatieLunara / Commercial
   - GanttPlan / GanttWbsNod
   - LocatieProiect
   - HR assignments (AngajatProiect)
   - Documente (project documents)
   - BIM / Santier / ModelBIM / ElementBIM / ProiectSantier / Cladire
   - Fleet / ConsumUtilaj
   - feature flags (services.feature_flags)
   - guided-flow parcurs / next_idx / url_for
4. Identify which blocks (if any) are Project-owned.
5. Identify which blocks must remain route-owned (url_for / feature flags / parcurs / render).
6. Identify which blocks should remain delegated to existing tenant helpers / services.
7. Decide whether hub should remain route-resident.
8. Decide whether a separate cross-domain aggregator service is appropriate.
9. Identify collision risk with Contract / Commercial / Gantt / BIM domains.
10. Produce a no-code report only. Do not implement.
```

---

## Initial scope for the S1.5 gate

```text
- Project hub only
- no detalii changes
- no list/read/financial/helper changes
- no create/edit/status changes
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

Follow the S1.x service-extraction constraints (D014 + D015 + D016 + D017 + D018):
gate-first; preserve tenant guards and route behavior; HTTP-free services; reuse
existing tenant-safe query helpers / existing services for cross-domain reads; a
Project hub aggregator that reaches into other domains must NOT absorb those
domains' read semantics into project_service without explicit approval.

---

## No-touch boundaries for the S1.5 gate

```text
- do not modify code, tests, routes, services, forms
- do not modify models / migrations / templates / static / frontend
- do not start S1.5 implementation
- do not start hub extraction / aggregator implementation
- do not start Contract / Commercial / Gantt / BIM extraction
- do not touch Activity / Timesheet services
- do not alter the approved S1.3 / S1.4A project boundary
```

---

## Do not start

Do not start any implementation. The current authorized task is ONLY the S1.5
Project hub cross-domain no-code understanding / collision-safety gate (report
only). Any follow-up implementation requires a separate explicit approval from Albert.
