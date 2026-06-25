# Edifico PR Checklist

## General

- [ ] PR has one clear purpose.
- [ ] Scope matches prompt or issue.
- [ ] No unrelated refactor.
- [ ] No stack change.
- [ ] No microservice/background-worker dependency added.
- [ ] PythonAnywhere compatibility preserved.

## Product direction

- [ ] Change supports Construction Operating System direction.
- [ ] Does not make BIM mandatory.
- [ ] Does not create duplicate execution truth.
- [ ] Does not introduce `ExecutionTask` without ADR.
- [ ] Preserves execution spine.

## Tenant/security

- [ ] No tenant-owned raw `get_or_404(id)` added.
- [ ] Tenant-owned queries are scoped.
- [ ] Strict mode fails closed.
- [ ] Off mode remains compatible.
- [ ] Batch operations are tenant-safe.
- [ ] Downloads/exports are authorized before file generation/serving.
- [ ] Two-tenant tests added when relevant.

## Services

- [ ] Business logic lives in service, not route.
- [ ] Route remains thin.
- [ ] Service accepts tenant context or scoped object.
- [ ] Service can be tested independently.

## Database

- [ ] Migration included if schema changed.
- [ ] Migration is backward compatible where possible.
- [ ] SQLite and MySQL compatibility considered.
- [ ] No dialect-specific SQL unless guarded/tested.

## Tests

- [ ] Unit tests added/updated.
- [ ] Integration tests added/updated.
- [ ] Tenant tests added if access changes.
- [ ] Targeted tests run.
- [ ] Unrun tests documented.

## Documentation

- [ ] Constitution/architecture docs updated if behavior changes.
- [ ] ADR created if decision changes.
- [ ] Prompt/implementation notes added when useful.

## Final response

- [ ] Files changed listed.
- [ ] Behavior changes listed.
- [ ] Tests run listed.
- [ ] Known limitations listed.
- [ ] Recommended next PR listed.
