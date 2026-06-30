# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.C4 Project Details Context Extraction Review
```

This is a REVIEW / NO-CODE validation task.

NO NEW IMPLEMENTATION IS AUTHORIZED. hub remains untouched and deferred; broad
Project Service extraction is NOT authorized.

S1.C4 reviews the completed S1.4A Project Details context boundary after:

```text
S1.4 Project Details / Cross-Domain Context No-Code Gate (approved)
S1.4A Project Details Context Extraction
```

Current canonical base commit:

```text
4c15b01 S1.4A project details context extraction
```

Current canonical branch:

```text
feat/s1.4a-project-details-context-extraction
```

---

## Previous completed step (S1.4A) — VALIDATED

```text
S1.4A Project Details Context Extraction
```

Verdict: COMPLETE. The detalii read-only context assembly was extracted into the
existing services/project_service.py (get_project_detail_context), without
touching hub, create/edit/status, list/read/financial helpers, forms, or any
other domain.

S1.4A recorded results:

```text
- get_project_detail_context(*, project, month, year, tenant_id=None) added (read-only)
- detalii route delegates context assembly; route keeps get_project_or_404,
  request.args (luna/anul), render_template, HTTP behavior
- service owns: team assignments (ordered), active assigned + available employees,
  dist_functii, monthly pontaje, ore_per_angajat aggregate, total_ore /
  ore_saptamanale / cost_manopera / cost_lunar (via S1.3A helpers), legacy documents
- exact 14 detalii render-context values preserved (proiect/luna/anul route-owned)
- ordering/filters/fallbacks preserved; ore_per_angajat keeps its db.session.query
  aggregate tenant-scoped via the query_timesheets_for_tenant() subquery
- service stays HTTP-free; S1.4A helper read-only (no add/delete/commit/rollback)
- no new raw Proiect/Pontaj/Angajat/RaportActivitate/Document.query in the service
- query_employees_for_tenant + query_legacy_documents_for_tenant removed from
  routes/proiecte.py imports (now resolved inside the service)
- hub untouched and deferred; lista / adauga / editeaza / schimba_status /
  financial wrappers / nested / raport / export_excel untouched
- forms / models / migrations / templates / static / frontend untouched
- Contract / Commercial / Gantt / BIM / Activity / Timesheet untouched
```

S1.4A validation:

```text
project service unit tests (test_project_service.py): 45 passed (34 prior + 11 new)
project targeted suite: 80 passed
cross-domain regression (timesheet routes + activity + timesheet service): 150 passed
Flask app smoke (proiecte routes): ok 27
full suite (tests/unit + tests/integration): 1178 passed, 39 skipped, 4 warnings
git diff --check clean
```

Files changed in 4c15b01:

```text
services/project_service.py
routes/proiecte.py
tests/unit/test_project_service.py
```

Test-fixture note: _curata also deletes Document rows for S13% projects; the
read-only guard now includes get_project_detail_context; the no-raw-query guard
now also asserts Document.query absent. Test-only, behavior-preserving.

---

## Goal of the current task (S1.C4 review)

Review the completed S1.4A Project Details context boundary (NO code):

```text
1. Review get_project_detail_context() in services/project_service.py.
2. Verify detalii context behavior (team / employees / dist_functii / pontaje /
   ore_per_angajat / financial / documents).
3. Verify routes/proiecte.py delegates only the detalii context (route keeps
   get_project_or_404, request.args, render_template, HTTP).
4. Verify hub was NOT touched.
5. Verify HTTP boundaries remain route-owned.
6. Verify tenant safety was preserved (off / optional / strict; foreign -> 404).
7. Verify the ore_per_angajat aggregate remains tenant-scoped via the
   query_timesheets_for_tenant() subquery.
8. Verify no raw tenant-owned queries were introduced (incl. Document.query).
9. Verify the helper is read-only (no add/delete/commit/rollback).
10. Verify tests are sufficient.
11. Identify any P0/P1 blockers.
12. If no P0/P1 blockers, approve S1.4A and recommend the next architectural step.
13. Produce a report only — no code.
```

---

## No-touch boundaries for the S1.C4 review

```text
- do not modify code / tests / routes / services / forms
- do not modify models / migrations / templates / static / frontend
- do not start hub extraction
- do not start broad Project Service extraction
- do not start Contract / Commercial / Gantt / BIM extraction
- do not alter completed S1.3 or S1.4A helpers
```

---

## Do not start

Do not start any new implementation. The current authorized task is ONLY the
S1.C4 review (report only). Any follow-up implementation requires a separate
explicit approval from Albert.
