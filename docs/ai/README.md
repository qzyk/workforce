# docs/ai — AI Coordination Layer

This folder exists so Claude Code, ChatGPT, Codex, and future AI agents work from the same source of truth.

Recommended usage:

1. Keep `PROJECT_STATE.md` updated after every PR or review.
2. Keep `DECISIONS_LOG.md` updated after every architectural/security decision.
3. Keep `CURRENT_TASK.md` updated with the only authorized next implementation task.
4. Keep `DO_NOT_TOUCH.md` strict.
5. Make Claude Code read these files before every coding session.

The root `CLAUDE.md` is the main Claude Code knowledge file.

Current required task:

```text
T1.14 Activity BIM Context Tenant Guard
```

Do not start:

```text
S1.1 Activity Service Extraction
```

until T1.14 and T1.C14 are complete and clean.
