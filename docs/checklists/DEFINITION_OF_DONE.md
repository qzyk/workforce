# Definition of Done

A change is done only when all applicable items are satisfied.

## Code

- Implementation is small and focused.
- No unrelated formatting churn.
- Existing behavior preserved unless explicitly changed.
- PythonAnywhere deployment assumptions preserved.

## Tests

- New behavior has tests.
- Refactored behavior has regression tests.
- Tenant-sensitive changes have cross-tenant tests.
- Test commands are documented.

## Security

- No new raw IDOR path.
- No unscoped export/download.
- No tenant-owned global aggregation.
- Strict mode behavior considered.

## Architecture

- Routes are thinner or unchanged.
- Services own business logic.
- Execution spine is respected.
- BIM remains context layer.
- No duplicate source of truth added.

## Documentation

- Relevant docs updated.
- ADR added for architectural decision changes.
- Known limitations documented.

## Review

- Risks are explicit.
- Rollback path is clear.
- Next recommended PR is identified.
