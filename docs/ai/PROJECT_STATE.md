# PROJECT_STATE.md — Canonical Project State for AI Agents

Last updated after:

```text
T1.14 Activity BIM Context Tenant Guard (completed)
```

Canonical repository:

```text
qzyk/workforce
```

Canonical worktree:

```text
/Users/albertciolacu/workforce-t1.5-contract
```

Do not work in:

```text
/Users/albertciolacu/workforce
```

External Claude worktrees:

```text
/Users/albertciolacu/workforce/.claude/worktrees/
```

Status of external Claude worktrees:

```text
External non-authoritative experimental worktrees.
Excluded from canonical reviews and implementation tasks.
Do not merge, clean, delete, or copy from them.
```

---

## Current canonical branch

```text
feat/t1.14-activity-bim-context-tenant-guard
```

## Current canonical HEAD

```text
818c90d T1.14 activity BIM context tenant guard
```

## Current test baseline

T1.14 completed. Test baseline from T1.C13 (T1.14 test results to be confirmed by T1.C14):

```text
229+ tenant tests passed (T1.C13 baseline)
63 location/API-token/audit/IoT regression tests passed
T1.14 added: activity BIM context + BIM element aggregation tests
```

---

## Completed tenant guard stack

```text
T1.1  tenant access foundation
T1.2  project tenant guard
T1.3  activity tenant guard
T1.4  timesheet tenant guard
T1.5  contract tenant guard
T1.6  document tenant guard
T1.7  BIM tenant guard
T1.8  Gantt tenant guard
T1.9  dashboard reporting tenant guard
T1.10 HR fleet tenant guard
T1.11 notifications admin tenant guard
T1.12 project nested tenant guard
T1.13 locations audit api tokens tenant guard
T1.14 activity BIM context tenant guard
```

---

## Current task

```text
T1.C14 Final Tenant Guard Review
```

Review the complete T1.1–T1.14 stack before approving S1.1.

## Next phase only if T1.C14 is APPROVED

```text
S1.1 Activity Service Extraction
```

---

## Current repository posture

Route-level tenant guard complete after T1.14.

Remaining accepted future categories:

```text
service-boundary hardening
historical data contamination cleanup
schema improvements for indirect ownership models
direct service tests for extracted services
```
