# 08 — Roadmap

## Strategic order

```text
Security foundation
  -> service boundaries
  -> execution spine link
  -> progress and delay
  -> proof of work
  -> reporting/cockpit
  -> AI and advanced automation
```

## Track A — Tenant Security

### T1.1 Tenant Access Foundation

- Create canonical tenant access helpers.
- Preserve mode off behavior.
- Add tests.
- Pilot on one project route.

### T1.2 Project Tenant Guard Expansion

- Protect project list/detail/hub/edit/status/export.
- Assign tenant on project creation.
- Add cross-tenant tests.

### T1.3 Activity Tenant Guard

- Protect RaportActivitate routes and lists.
- Preserve workflow.
- No service extraction yet.

### T1.4 Timesheet Tenant Guard

- Protect Pontaj routes and exports.
- Preserve workflow.

### T1.5 Contract Tenant Guard

- Protect Contract, ProgramReferinta, TaskProgram, SituatieLunara, Revendicare.

### T1.6 Document/File Tenant Guard

- Protect Document and DocumentProiect downloads/previews/exports.

### T1.7 BIM/Gantt Tenant Hardening

- Protect BIM file/tree/search/export routes.
- Validate Gantt project association.

## Track B — Service Architecture

### S1.1 Activity Service

- Extract create/update/submit/approve/reject for RaportActivitate.

### S1.2 Timesheet Service

- Extract hour calculation, create/update/submit/approve/reject for Pontaj.

### S1.3 Project Metrics Service

- Extract hub/list/detail metrics.

### S2.1 Baseline Service

- Extract ProgramReferinta/TaskProgram import/versioning.

### S2.2 Gantt Plan Service

- Safe GanttPlan operations.

### S3.1 Contract Service

- Contract and monthly situation workflows.

### S3.2 Document Service

- Upload/download/revision authorization.

### S3.3 BIM Issue Service

- Field issues and BIM issue workflow.

### S4.1 Reporting Service

- Export/report DTOs and file generation.

## Track C — Product Spine

### P1.1 Link RaportActivitate to TaskProgram

- Add nullable `task_program_id`.
- Manual linking.
- Tests.

### P1.2 Task Progress Service

- Approved reports aggregate into task progress read model.

### P1.3 Baseline Approval

- Operationalize `ProgramReferinta.aprobat`.

### P1.4 Plan vs Actual

- Task-level planned vs actual reporting.

## Track D — Operational Intelligence

### D1.1 Delay Domain MVP

- First-class delay model.
- Link to project/task/term/report.

### D1.2 Delay Detection

- Read-only detection from planned vs actual.

### D1.3 Delay Approval

- Confirm/approve/reject/close delay.

### D1.4 Claims Link

- Delay -> Revendicare.

## Track E — Proof of Work

### W1.1 Activity Attachments

- Photos/files on RaportActivitate.

### W1.2 Supervisor confirmation

- Separate field-level confirmation from manager approval.

### W1.3 Immutable monthly closure

- Lock snapshot after emission.

## Track F — Executive Cockpit

### R1.1 Cockpit read model

- Project risk;
- delays;
- approvals pending;
- plan vs actual;
- cost indicators;
- missing reports.

### R1.2 Dashboard UI

- Lightweight server-rendered dashboard.

## Track G — AI Later

Only after Tracks A-F have mature data.

AI initiatives:

- Gantt suggestions;
- technical proposal drafts;
- delay narrative drafting;
- claim evidence summaries;
- productivity insights.

## What not to prioritize

- advanced BIM;
- Digital Twin;
- IoT expansion;
- microservices;
- SPA rewrite;
- Celery/Redis dependency;
- AI replacing human approval.
