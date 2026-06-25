# 07 — BIM Strategy

## Position

BIM is a **context layer**.

It is not the primary product and not the execution source of truth.

## BIM may provide

- spatial location;
- element references;
- model viewing;
- issue context;
- quantity hints;
- discipline context;
- CDE-like document/model version context;
- optional field visualization.

## BIM must not

- block workforce reporting;
- become the only way to create work reports;
- replace TaskProgram;
- replace RaportActivitate;
- replace contract baseline;
- become the focus before tenant security;
- expand into advanced Solibri/Navisworks-like geometry engines now.

## Current BIM risk

The BIM module is broad and contains many subdomains in one route module:

- hierarchy;
- models;
- viewer;
- CDE-ish workflow;
- rules;
- clash;
- IoT;
- 4D/5D;
- realtime;
- BCF;
- COBie;
- API tokens;
- RBAC.

This is powerful but dangerous if not bounded.

## Target BIM boundaries

### `bim_service.py`

- hierarchy read models;
- site/model/element detail DTOs;
- viewer file descriptor;
- BIM context for execution screens.

### `bim_issue_service.py`

- issue lifecycle;
- field issue creation;
- comments;
- BCF import/export scoped by tenant;
- Kanban grouping;
- audit/realtime hooks.

### `bim_import_service.py`

- IFC upload validation;
- model creation;
- import orchestration;
- external mapping;
- QTO extraction.

## BIM + execution integration

Allowed integration points:

```text
RaportActivitate -> optional ElementBIM / Spatiu / Zona
Pontaj -> optional ElementBIM / Spatiu / Zona
IssueBIM -> optional TaskProgram/RaportActivitate later
TaskProgram -> optional BIM context later
```

Do not make BIM mandatory.

## BIM tenant safety

BIM must be treated as high sensitivity.

- Model files can reveal full building geometry.
- BCF exports can reveal issues, responsibilities, and project status.
- Search/tree APIs can leak project existence and scale.

Every BIM file/export/detail route must be tenant-scoped before multi-company SaaS use.

## Deferred features

Do not expand now:

- advanced Digital Twin;
- IoT analytics;
- advanced clash detection;
- COBie as core sales feature;
- public API expansion;
- APS enterprise workflow;
- complex real-time collaboration.

These may return after the execution spine is stable.
