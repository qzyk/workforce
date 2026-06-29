# DO_NOT_TOUCH.md — Protected Areas and Prohibited Changes

This file defines protected areas for Claude Code.

Unless the current task explicitly allows it, do not touch these files or domains.

---

## 1. Never touch without explicit permission

```text
models.py
migrations/
config.py
requirements.txt
app.py
```

Exceptions require explicit task approval.

---

## 2. Do not change architecture

Do not introduce:

```text
microservices
frontend rewrite
Celery
Redis
event bus
workflow engine
new ExecutionTask model
```

---

## 3. Do not start service extraction unless current task says so

Do not create:

```text
activity_service.py
timesheet_service.py
project_service.py
project_metrics_service.py
contract_service.py
baseline_service.py
claims_service.py
document_service.py
bim_service.py
gantt_plan_service.py
reporting_service.py
notification_service.py
admin_service.py
user_service.py
fleet_service.py
location_service.py
audit_service.py
api_token_service.py
iot_service.py
```

Current task does not allow service extraction.

---

## 4. Current T1.14 allowed files

For current task `T1.14 Activity BIM Context Tenant Guard`, allowed files should be limited to:

```text
services/security/tenant_access.py
routes/activitati.py
routes/bim.py
tests/unit/test_tenant_access_activity_bim_context.py
tests/integration/test_tenant_access_activity_bim_context_routes.py
docs/architecture/tenant_access_foundation.md
```

If another file appears necessary, stop and explain why before editing.

---

## 5. Do not touch external Claude worktrees

Do not touch:

```text
/Users/albertciolacu/workforce/.claude/worktrees/
```

Do not copy from those worktrees.

---

## 6. Do not change business workflows

Do not change:

```text
activity approval statuses
timesheet approval statuses
contract status workflow
document approval workflow
BIM import semantics
Gantt algorithms
report/export layouts
file storage paths
```

unless explicitly requested.

---

## 7. No schema changes during current task

Do not:

```text
add migrations
change columns
add tenant_id columns
modify constraints
rename models
```

---

## 8. Tenant guard must preserve off mode

For any security task:

```text
MULTI_TENANT_MODE=off must preserve legacy behavior.
```

---

## 9. Stop conditions

Stop and report if:

- canonical worktree is dirty before starting;
- current HEAD does not match `PROJECT_STATE.md`;
- branch is not the expected task branch;
- unexpected files need editing;
- tests fail in a way unrelated to the task;
- schema change seems necessary;
- old Claude worktrees appear to be required;
- instructions conflict.
