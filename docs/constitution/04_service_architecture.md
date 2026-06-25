# 04 — Service Architecture

## Goal

Move Edifico from route-heavy behavior to service-owned business logic.

## Target shape

```text
routes/*
  -> services/security/tenant_access.py
  -> services/projects/project_service.py
  -> services/projects/project_metrics_service.py
  -> services/execution/activity_service.py
  -> services/execution/timesheet_service.py
  -> services/execution/task_progress_service.py
  -> services/contracts/contract_service.py
  -> services/contracts/baseline_service.py
  -> services/contracts/claims_service.py
  -> services/documents/document_service.py
  -> services/planning/gantt_plan_service.py
  -> services/reporting/reporting_service.py
  -> services/bim/bim_service.py
  -> services/bim/bim_issue_service.py
  -> services/bim/bim_import_service.py
```

## Service law

Services are business boundaries.

Routes may:

- authenticate;
- parse request payload;
- call service;
- handle flash/redirect/render/send_file/json.

Routes must not:

- calculate business totals;
- validate domain workflows;
- mutate status directly;
- approve/reject directly;
- generate XLSX/PDF cells;
- query tenant-owned records directly;
- duplicate business rules.

## Phase S1 services

### `services/security/tenant_access.py`

Purpose:

- fail-closed tenant record access;
- project/activity/timesheet/contract/document/BIM scoped getters;
- central place to prevent IDOR.

### `services/execution/activity_service.py`

Purpose:

- create/update `RaportActivitate`;
- submit/approve/reject;
- batch approval;
- delete policy;
- future audit;
- future TaskProgram link.

### `services/execution/timesheet_service.py`

Purpose:

- calculate hours;
- detect day type;
- duplicate validation;
- create/update/submit/approve/reject `Pontaj`;
- support `/teren/pontaj`.

### `services/projects/project_metrics_service.py`

Purpose:

- build project hub DTO;
- project list stats;
- project detail metrics;
- avoid multi-table aggregations in routes.

## Phase S2 services

### `services/projects/project_service.py`

Purpose:

- project create/update/status;
- employee assignment lifecycle;
- site link/unlink;
- project-level policies.

### `services/contracts/baseline_service.py`

Purpose:

- import and version `ProgramReferinta`;
- create/maintain `TaskProgram`;
- baseline approval;
- rebaseline later.

### `services/planning/gantt_plan_service.py`

Purpose:

- safe GanttPlan save/list/open;
- validate project association;
- bridge GanttPlan to ProgramReferinta later.

## Phase S3 services

### `services/contracts/contract_service.py`

Purpose:

- contract CRUD workflows;
- terms;
- offers;
- monthly quantities;
- monthly situations;
- status transitions.

### `services/contracts/claims_service.py`

Purpose:

- claims lifecycle;
- claim-task/term/quantity links;
- future link from Delay Domain.

### `services/documents/document_service.py`

Purpose:

- file upload metadata;
- download authorization;
- revision lifecycle;
- storage namespace.

### BIM services

BIM must be split into:

- `bim_service.py` for hierarchy/viewer/read models;
- `bim_issue_service.py` for issues/comments/BCF;
- `bim_import_service.py` for IFC import/QTO/mapping.

## Phase S4 services

### `services/reporting/reporting_service.py`

Purpose:

- produce DTOs and files;
- never accept unscoped IDs;
- return file descriptors, not Flask responses.

### `services/reporting/dashboard_service.py`

Purpose:

- executive cockpit;
- tenant-safe operational metrics;
- plan vs actual;
- delay and approval metrics.

## Service design rules

1. Services accept `tenant_id` or scoped domain objects.
2. Services should validate tenant again for write/export operations.
3. Services must not depend on templates.
4. Services should return DTOs/results/errors, not Flask responses.
5. Services should be testable with unit/integration tests.
6. Services should not hide database commits unpredictably; transaction behavior must be explicit.
7. Services must preserve PythonAnywhere compatibility.

## Example service result shape

```python
@dataclass
class ServiceResult:
    ok: bool
    value: object | None = None
    error: str | None = None
    code: str | None = None
```

This is optional, but route responses should not need to understand internal implementation details.
