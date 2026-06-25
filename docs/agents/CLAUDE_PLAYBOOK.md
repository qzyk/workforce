# Claude Code Playbook — Edifico

## Role

Claude should be used as:

- architecture reviewer;
- large-code reasoning assistant;
- refactor planner;
- prompt generator;
- audit generator;
- edge-case analyst;
- test strategy designer.

Claude may implement code, but only with constrained prompts and review.

## Best uses

1. Generate audits before major refactors.
2. Compare architecture options.
3. Produce migration plans.
4. Review Codex PRs conceptually.
5. Create test matrices.
6. Identify hidden coupling.
7. Draft ADRs.

## Avoid using Claude for

- large blind rewrites;
- unconstrained implementation;
- adding entire domains in one pass;
- changing DB schema without migration plan;
- replacing architecture decisions;
- making business direction decisions without ADR.

## Claude review checklist

When reviewing a proposed change, Claude must answer:

1. Does this preserve execution spine?
2. Does this preserve tenant safety?
3. Does this introduce duplicate truth?
4. Does this move logic out of routes or add more route logic?
5. Does this preserve PythonAnywhere compatibility?
6. Does this require migration?
7. Does this have tests?
8. Does this need an ADR?

## Claude architecture prompt skeleton

```text
You are reviewing a proposed Edifico PR.
Read docs/constitution first.
Assess whether this PR violates:
- execution spine;
- tenant security;
- service architecture;
- no rewrite rule;
- BIM context layer rule.
Return:
1. approval/rejection recommendation;
2. blockers;
3. risk level;
4. tests missing;
5. architecture notes.
```

## Claude audit prompt skeleton

```text
Do not write code.
Audit [domain].
Use the Edifico Constitution.
Produce docs/audits/[name].md.
Focus on:
- current behavior;
- risks;
- exact files/functions;
- recommended PR order;
- tests needed.
```

## Claude implementation prompt rule

If Claude writes code, every prompt must include:

- exact scope;
- forbidden files;
- allowed files;
- tests required;
- docs required;
- no broad refactor clause;
- stop condition.

## Claude output standard

Claude must never claim a feature works unless:

- code exists;
- tests exist;
- route/service behavior is verified;
- migration status is clear.

Use labels:

- VERIFIED
- PARTIALLY VERIFIED
- NOT VERIFIED
- ASSUMPTION
- RISK
