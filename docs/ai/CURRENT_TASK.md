# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.C3 Project Service Extraction Review
```

This is a REVIEW / NO-CODE validation task.

NO NEW IMPLEMENTATION IS AUTHORIZED. Broad Project Service extraction is NOT
authorized.

S1.C3 reviews the completed S1.3 Project Service boundary after:

```text
S1.3A Project Service Read/List + Financial Data Assembly Extraction
S1.3B Project Create/Edit/Status Save Extraction
```

Current canonical base commit:

```text
a9fabfc S1.3B project create edit status extraction
```

Current canonical branch:

```text
feat/s1.3b-project-create-edit-status-extraction
```

---

## Previous completed step (S1.3B) — VALIDATED

```text
S1.3B Project Create/Edit/Status Save Extraction
```

Verdict: COMPLETE. The adauga/editeaza/schimba_status save logic was extracted
into the existing services/project_service.py with service-commit / route-rollback,
without touching list/read/financial helpers, forms, cross-domain routes, or any
other domain.

S1.3B recorded results:

```text
- create_project_from_form_data(), update_project_from_form_data(),
  change_project_status() added; private _compose_project_location() and
  _validate_project_manager() added
- adauga / editeaza / schimba_status valid-save branches delegate to the service
- route owns ProiectForm, validate_on_submit, request.form/get_json, flash,
  redirect, url_for, render_template, jsonify, HTTP codes
- auto cod_proiect GET pre-fill (global Proiect.query count) route-owned, unchanged
- editeaza GET locatie split route-owned, unchanged
- invalid schimba_status stays non-exception route-owned JSON 400 (no mutation/commit)
- service-commit / route-rollback applied (each mutator commits once; route wraps
  service calls in HTTPException/Exception -> rollback; raise)
- create resolves tenant_id via tenant_id_for_new_record_or_403() (fail-closed);
  edit/status operate on the route's get_project_or_404() object (foreign -> 404)
- manager validation via query_users_for_tenant().first_or_404() (no blind trust)
- finalizat sets data_sfarsit_real only when unset; existing value not overwritten
- no raw Proiect/Pontaj/Angajat/RaportActivitate.query introduced in the service
- forms/proiecte_forms.py untouched; lista + S1.3A read/list + financial helpers untouched
- detalii / hub / nested / raport / export_excel untouched
- Contract / Commercial / Gantt / Activity / Timesheet untouched
- models / migrations / templates / static / frontend untouched
```

S1.3B validation:

```text
project service unit tests (test_project_service.py): 34 passed (19 S1.3A + 15 S1.3B)
project targeted suite (service + route/nested/hub/locations): 69 passed
regression safety (activity + timesheet + timesheet routes): 150 passed
Flask app smoke (proiecte routes): ok 27
full suite (tests/unit + tests/integration): 1167 passed, 39 skipped, 4 warnings
git diff --check clean
```

Files changed in a9fabfc:

```text
services/project_service.py
routes/proiecte.py
tests/unit/test_project_service.py
```

Test-fixture note: `_curata` cleanup broadened 'S13A-%' -> 'S13%'; the S1.3A
HTTP-free/read-only guard scoped to the read-only functions (mutators now commit).
Test-only, behavior-preserving, validated by the full suite.

---

## Goal of the current task (S1.C3 review)

Review the completed S1.3 Project Service boundary (NO code):

```text
1. Review services/project_service.py as the current Project service boundary.
2. Verify read/list context behavior (S1.3A).
3. Verify financial helper behavior (S1.3A).
4. Verify create/edit/status behavior (S1.3B).
5. Verify routes/proiecte.py delegates the intended slices (lista, financial
   wrappers, adauga, editeaza, schimba_status).
6. Verify HTTP boundaries remain route-owned (ProiectForm/validate_on_submit/
   request/flash/redirect/render/jsonify/HTTP codes; auto-code prefill; GET split).
7. Verify tenant safety across off / optional / strict (and foreign -> 404 / fail-closed).
8. Verify no raw tenant-owned queries were introduced in the service
   (the auto-code Proiect.query stays route-owned; forms untouched).
9. Verify the service-commit / route-rollback convention is consistent; invalid
   status stays a non-exception JSON 400.
10. Verify tests are sufficient.
11. Identify any P0/P1 blockers.
12. If no P0/P1 blockers, approve S1.3A/S1.3B and recommend the next architectural step.
13. Produce a report only — no code.
```

---

## No-touch boundaries for the S1.C3 review

```text
- do not modify code / tests / routes / services / forms
- do not modify models / migrations / templates / static / frontend
- do not start S1.3C or broad Project Service extraction
- do not start detalii / hub / nested / report extraction
- do not start Contract / Commercial / Gantt extraction
- do not alter completed S1.3A / S1.3B helpers
```

---

## Do not start

Do not start any new implementation. The current authorized task is ONLY the
S1.C3 review (report only). Any follow-up implementation requires a separate
explicit approval from Albert.
