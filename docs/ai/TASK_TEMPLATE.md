# TASK_TEMPLATE.md — Prompt Template for Claude Code

Use this template for every new implementation task.

---

You are Claude Code acting as a senior engineer on the Edifico / Workforce repository.

Before doing anything, read:

```text
CLAUDE.md
docs/ai/PROJECT_STATE.md
docs/ai/DECISIONS_LOG.md
docs/ai/CURRENT_TASK.md
docs/ai/DO_NOT_TOUCH.md
docs/architecture/tenant_access_foundation.md
```

Then run:

```bash
cd /Users/albertciolacu/workforce-t1.5-contract
git status
git branch --show-current
git log --oneline -30
git worktree list
```

External Claude worktrees under `/Users/albertciolacu/workforce/.claude/worktrees/` are non-authoritative. Do not merge, delete, clean, or copy from them.

If the canonical worktree is dirty, stop.

Task:

```text
<INSERT TASK NAME>
```

Expected base commit:

```text
<INSERT COMMIT HASH AND MESSAGE>
```

Expected branch:

```text
<INSERT BRANCH NAME>
```

Allowed files:

```text
<INSERT ALLOWED FILES>
```

Forbidden:

```text
No schema changes.
No migrations.
No service extraction unless explicitly allowed.
No unrelated files.
No workflow changes.
No export layout changes.
No external Claude worktree use.
```

Run tests:

```bash
<INSERT TEST COMMANDS>
```

If all tests pass and only allowed files changed:

```bash
git add <allowed files>
git commit -m "<commit message>"
```

Completion report must include:

1. Branch/worktree used.
2. Base commit.
3. Files changed.
4. Helpers added or reused.
5. Main safeguards or changes.
6. Behavior by tenant mode.
7. Tests added.
8. Tests run.
9. Known limitations.
10. Remaining risks.
11. Commit hash if committed.
12. Final verdict.
