# 03 — Tenant Security Constitution

## Supreme rule

> No cross-tenant data leakage.

Everything else is secondary.

## Current risk profile

The audits found that Edifico has tenant-aware infrastructure but does not yet enforce tenant boundaries uniformly.

Known risks:

- `with_tenant_scope` must be called explicitly;
- many routes use `Model.query.get_or_404(id)`;
- several core legacy models do not have direct `tenant_id`;
- many tenant columns are nullable;
- reports and exports can aggregate globally;
- file storage is shared and ownership checks depend on route validation;
- BIM hierarchy is partly indirectly tenant-owned;
- strict mode is not yet production-safe.

## Tenant modes

### off

Legacy single-tenant behavior.

Rules:

- do not aggressively filter;
- do not break existing deployments;
- acceptable for one company per deployment/database.

### optional

Migration mode.

Rules:

- apply tenant filtering when tenant exists;
- do not assume all legacy rows are safe;
- include global rows only when explicitly allowed.

### strict

SaaS mode.

Rules:

- fail closed;
- no tenant context means no tenant-owned data;
- `tenant_id=NULL` is not customer data unless explicitly declared global;
- ID guessing must not reveal existence;
- batch operations must reject mixed-tenant IDs;
- services must require tenant context.

## Canonical access pattern

```text
route receives id
  -> tenant_access.get_*_or_404(id, tenant_id)
  -> service receives scoped object or tenant-scoped id
  -> service validates tenant again before mutation/export
  -> route renders/sends response
```

## Forbidden pattern

```python
obj = Model.query.get_or_404(id)
```

Forbidden for tenant-owned objects unless explicitly global catalog data.

## Direct vs indirect tenant ownership

### Direct ownership

Model has `tenant_id`.

Examples:

- `Proiect`
- `Contract`
- `ProgramReferinta`
- `TaskProgram`
- many contract/BIM/Gantt models

### Indirect ownership

Model derives tenant through another model.

Examples:

- `RaportActivitate` through `Proiect` / `Angajat`;
- `Pontaj` through `Proiect` / `Angajat`;
- `DocumentProiect` through `Proiect`;
- `ElementBIM` through `Santier` / `ModelBIM` / hierarchy.

For v1, indirect ownership must be implemented through explicit scoped helpers. Do not invent ad-hoc joins in every route.

## Global rows

`tenant_id=NULL` is allowed only for:

- true global catalogs;
- system defaults;
- public configuration templates;
- explicitly reviewed global data.

It is not allowed for customer-owned projects, contracts, activities, timesheets, documents, BIM files, or reports.

## Tenant roadmap

### T1 — Access foundation

- Create canonical tenant access helpers.
- Protect project routes first.

### T2 — Execution/workforce isolation

- Protect `RaportActivitate` and `Pontaj`.
- Add direct `tenant_id` later if needed.

### T3 — Contracts/documents/files

- Scope contract routes.
- Scope financial exports.
- Scope downloads.
- Namespace storage or enforce ownership before every `send_file`.

### T4 — BIM/Gantt hardening

- Scope BIM tree/search/viewer/file APIs.
- Scope BCF/COBie exports.
- Validate Gantt project association.

## Tests required

Every protected route must have two-tenant tests:

- tenant A can access own record;
- tenant A cannot access tenant B record;
- tenant A cannot mutate tenant B record;
- tenant A cannot export tenant B record;
- strict mode fails closed;
- off mode remains legacy compatible.

## Security principle

> UI hiding is not security. Every route and service must enforce access.


## Implementation status — T1.1 and T1.2

The canonical tenant access layer has been introduced as:

```text
services/security/tenant_access.py
```

The architecture documentation for this implementation is stored at:

```text
docs/architecture/tenant_access_foundation.md
```

### Available primitives

- `get_current_tenant_id_safe()`
- `get_tenant_mode()`
- `is_super_admin(user)`
- `model_has_tenant_id(model)`
- `query_for_tenant(model, tenant_id=None, include_global=False)`
- `get_or_404_for_tenant(model, object_id, tenant_id=None, include_global=False)`
- `ensure_same_tenant(obj, tenant_id=None, include_global=False)`
- `require_same_tenant(obj, tenant_id=None, include_global=False)`
- `get_project_or_404(project_id, tenant_id=None)`
- `tenant_id_for_new_record_or_403()`

### T1.2 project route integration completed

The following project routes are now documented as tenant-guarded:

- `proiecte.lista`
- `proiecte.adauga`
- `proiecte.detalii`
- `proiecte.hub`
- `proiecte.editeaza`
- `proiecte.schimba_status`
- `proiecte.export_excel`

### Important limitation

T1.2 protects project lookup and core project route access. It does not yet protect all nested project-domain data such as employee assignments, legacy documents, resource/vehicle data, BIM links, EVM/report aggregates, or contract/Gantt/BIM/document records read inside the project hub. These require dedicated helpers because several of those models use indirect tenant ownership.
