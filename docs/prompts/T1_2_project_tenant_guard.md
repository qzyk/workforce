# Prompt — T1.2 Project Tenant Guard Expansion

Use this prompt after T1.1.

Core objective:

Protect project list/detail/hub/edit/status/export routes using tenant access foundation.

Rules:

- Do not touch activities/timesheets/contracts/BIM.
- No schema changes.
- Preserve mode off.
- Add strict-mode project IDOR tests.

## Implementation result imported from Codex T1.2

The implementation documentation now lives in:

```text
docs/architecture/tenant_access_foundation.md
```

### Confirmed protected project routes

| Route | Status |
|---|---|
| `proiecte.lista` | Uses `query_for_tenant(Proiect)` for listing and statistics. |
| `proiecte.adauga` | Assigns `tenant_id` for new projects in optional/strict when a tenant exists. |
| `proiecte.detalii` | Uses `get_project_or_404(id)`. |
| `proiecte.hub` | Uses `get_project_or_404(id)`. |
| `proiecte.editeaza` | Uses `get_project_or_404(id)`. |
| `proiecte.schimba_status` | Uses `get_project_or_404(id)` before mutation. |
| `proiecte.export_excel` | Uses `get_project_or_404(id)` before export generation. |

### Confirmed behavior

- `off`: legacy single-tenant compatibility remains.
- `optional`: filtering applies when a current tenant exists.
- `strict`: foreign-tenant projects return 404; normal users without tenant cannot create tenant-owned projects.
- super-admin behavior remains explicit: admin without `tenant_id` can see unfiltered project data and create global `tenant_id=NULL` projects.

### Remaining project-related risks

T1.2 did not protect nested child-domain aggregations. These must be handled through separate helpers because many are indirect tenant-owned models:

- `AngajatProiect` assignments;
- legacy project `Document` records;
- project resource and vehicle data;
- project/BIM links;
- EVM/report aggregates;
- contracts/Gantt/BIM/document data read inside project hub;
- manager dropdowns and form choices;
- exports/reports aggregating models without direct `tenant_id`.

## Next recommended prompt

Run T1.3 Activity Tenant Guard, focused on `RaportActivitate` access through indirect ownership via `Proiect` and `Angajat`, without service extraction and without schema changes.
