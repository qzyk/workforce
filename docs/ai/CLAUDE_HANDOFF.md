# CLAUDE_HANDOFF.md — Mandatory Handoff Protocol

Use this protocol for every Claude Code session.

---

## 1. Start of session checklist

Before coding, Claude must read:

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
git status
git branch --show-current
git log --oneline -30
git worktree list
```

Expected canonical worktree:

```text
/Users/albertciolacu/workforce-t1.5-contract
```

If the canonical worktree is dirty, stop and report.

---

## 2. External worktrees rule

External Claude worktrees under:

```text
/Users/albertciolacu/workforce/.claude/worktrees/
```

are non-authoritative experiments.

Do not:

- inspect them as source of truth;
- merge them;
- delete them;
- clean them;
- copy code from them.

Mention them only as excluded from canonical scope.

---

## 3. Before coding

Claude must state:

1. current branch;
2. current HEAD;
3. intended task;
4. allowed files;
5. whether the worktree is clean.

If branch or HEAD conflicts with `PROJECT_STATE.md`, stop.

---

## 4. During coding

Keep changes narrow.

Do not touch unrelated files.

Prefer existing helper functions over new logic.

For tenant guard work, use:

```text
services/security/tenant_access.py
```

Do not duplicate tenant filtering unless there is no existing helper.

---

## 5. Before commit

Run:

```bash
git status
git diff --stat
git diff --name-only
git diff --check
```

Run required tests from `docs/ai/CURRENT_TASK.md`.

Stage only allowed files.

Check staged files:

```bash
git diff --cached --name-only
```

If unrelated files are staged or dirty, stop.

---

## 6. Completion report format

Every task must end with:

```text
# <Task Name> Completion Report

1. Branch/worktree used
2. Base commit
3. Files changed
4. Helpers added or reused
5. Main safeguards or changes
6. Behavior by tenant mode
7. Tests added
8. Tests run
9. Known limitations
10. Remaining risks
11. Commit hash if committed
12. Final verdict
```

---

## 7. Roadmap decision rule

Claude does not decide roadmap alone.

Claude may recommend the next step, but the canonical next task is updated only in:

```text
docs/ai/PROJECT_STATE.md
docs/ai/CURRENT_TASK.md
```

If unsure, stop and report.
