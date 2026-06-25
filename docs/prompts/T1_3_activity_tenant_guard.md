# Prompt — T1.3 Activity Tenant Guard

## Context

T1.1 and T1.2 are complete.

## Objective

Protect `RaportActivitate` routes and lists with tenant-safe access.

## Scope

Allowed:

- `routes/activitati.py`
- `services/security/tenant_access.py` small helper additions
- tests
- docs

Forbidden:

- no service extraction;
- no schema changes;
- no migrations;
- no timesheet changes;
- no contract/BIM/Gantt changes;
- no template changes unless test-proven necessary.

## Requirements

- Protect detail/edit/delete/submit/approve/reject routes.
- Protect batch approval.
- Scope lists/panels/calendar/API endpoints.
- Preserve off mode behavior.
- In strict mode, tenant A cannot access tenant B activities.
- If `RaportActivitate` lacks tenant_id, use Proiect ownership path.
- Add tests for same-tenant and cross-tenant behavior.
- Document indirect ownership path.

## Expected output

- files changed;
- routes protected;
- tests added/run;
- limitations;
- next PR recommendation.
