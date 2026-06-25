# ADR-0003 — Tenant Safety Before New Features

## Status

Accepted.

## Context

The tenant audit found tenant-aware infrastructure but incomplete enforcement across routes, services, exports, and files.

## Decision

No major multi-company feature work should proceed before the tenant access foundation and core project/execution guards are implemented.

## Consequences

Immediate order:

1. tenant access foundation;
2. project guard;
3. activity guard;
4. timesheet guard;
5. contracts/documents/files;
6. BIM/Gantt hardening.

## Non-goals

This ADR does not require rewriting all modules at once.

The implementation must be incremental.
