# CURRENT_TASK.md — Current Authorized Task

Current authorized task:

```text
S1.C1 Activity Service Extraction Review
```

This is a REVIEW checkpoint over the completed S1.1 activity service boundary
(S1.1A–S1.1D). It is read-only: it produces a review verdict, not new feature
code. A fix is allowed only if the review finds a CRITIC/MAJOR issue, and only
within the activity service boundary already established.

IMPORTANT: S1.2 TIMESHEET SERVICE EXTRACTION IS NOT YET AUTHORIZED.
S1.2 may start only after S1.C1 reviews and approves the completed S1.1
activity service boundary, and after a separate no-code safety gate is
approved by Albert.

Current canonical base commit:

```text
1c854f6 S1.1D activity report export data extraction
```

Current canonical branch:

```text
feat/s1.1d-activity-report-export-extraction
```

---

## Previous step (S1.1D) — VALIDATED

```text
S1.1D Activity Reports / Exports Data Assembly Extraction
```

Validated by Albert based on the completion report.

S1.1D summary:

```text
- added get_activity_rows_for_period() to services/activity_service.py
- added get_timesheet_hours_map_for_period()
- added get_project_activity_report_data()
- extracted tenant-safe data assembly from raport_saptamanal, raport_lunar,
  raport_anual, raport_proiect
- preserved T1.C14 monthly timesheet scoping via query_timesheets_for_tenant()
- left export_edifico and export_edifico_preview in routes intentionally for
  layout stability
- left layout/styling helpers in routes intentionally
- no schema/migration/template/layout/file-name changes
- no save/workflow/read-context changes
- no Pontaj/BIM/Contract/Gantt/HR/Fleet changes
- no S1.2 started
```

Tests reported:

```text
40 activity service tests passed
5 export layout regression tests passed
246 tenant tests passed
127 targeted/regression/smoke tests passed
app import and 25 activitati routes OK
```

---

## Completed S1.1 activity service boundary (subject of S1.C1)

```text
S1.1A Activity Service Skeleton + Read/Form Context Extraction
S1.1B Activity Create/Edit Save Extraction
S1.1C Activity Workflow Transition Extraction
S1.1D Activity Reports / Exports Data Assembly Extraction
```

Service surface in services/activity_service.py:

```text
get_current_employee_for_user
get_activity_panel_context
get_activity_form_context
save_activity_from_form_data (+ ActivityValidationError)
submit_activity_for_approval
approve_activity
reject_activity
bulk_transition_activities
get_activity_rows_for_period
get_timesheet_hours_map_for_period
get_project_activity_report_data
```

---

## Goal of S1.C1 (review)

Review the completed S1.1 activity service boundary for:

1. Tenant-safety coverage (off/optional/strict; foreign IDs 404; fail-closed;
   T1.C14 monthly timesheet scoping preserved).
2. Behavior preservation (routes still own HTTP; flash/redirect/jsonify/send_file/
   templates/layout unchanged; statuses and workflows intact).
3. Boundary consistency (no raw tenant-owned queries in new service code; helpers
   from services/security/tenant_access.py reused).
4. Test adequacy (direct service tests + regressions green).
5. Accepted deferrals (export_edifico cluster left in routes — confirm acceptable).

Output: APPROVED (→ authorize S1.2 planning) or BLOCKED with reason. Only a
CRITIC/MAJOR finding justifies a code fix, scoped to the activity service
boundary.

---

## Do not start

Do not start:

```text
S1.2 Timesheet Service Extraction
Timesheet service work of any kind
BIM / Contract / Gantt service hardening
```

The current authorized task is ONLY S1.C1 (review). S1.2 requires S1.C1
approval plus a separate explicit implementation approval.
