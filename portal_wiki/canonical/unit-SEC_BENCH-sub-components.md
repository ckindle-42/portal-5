---
id: unit-SEC_BENCH-sub-components
kind: what
title: 'Security bench sub-components: capability index, goal-driven decide, drift
  gate, loop notifications'
sources:
- type: code
  path: portal/modules/security/core/capability/__init__.py
- type: code
  path: portal/modules/security/core/capability/index.py
- type: code
  path: portal/modules/security/core/capability/cli.py
- type: code
  path: portal/modules/security/core/capability/render.py
- type: code
  path: portal/modules/security/core/capability/tool_inventory.py
- type: code
  path: portal/modules/security/core/goal.py
- type: code
  path: portal/modules/security/core/goal_decide.py
- type: code
  path: portal/modules/security/core/goal_eval.py
- type: code
  path: portal/modules/security/core/drift_gate.py
- type: code
  path: portal/modules/security/core/drift_cli.py
- type: code
  path: portal/modules/security/core/loop.py
- type: code
  path: portal/modules/security/core/perception.py
- type: code
  path: portal/modules/security/core/objective_executor.py
- type: code
  path: portal/modules/security/core/objective_entry.py
last_generated_commit: 0a5fcb6eea38bf284a96ceea702849491ba4d1c7
claims: []
confidence: high
tags:
- bench
- security
- sub-components
- verified-v1
created_at: 1784945480.178221
updated_at: 1784945480.178221
---

## Capability Index

`portal.modules.security.core.capability` makes the scattered security library legible to a decide step. Read-only — indexes what already exists.

- `tool_inventory.py` — Kali tool arsenal curated from `config/tool_catalog.yaml`
- `index.py` — `Capability` dataclass + `build_index()` + `query()`
- `render.py` — `render_capabilities()` / `render_tool_arsenal()`
- CLI: `python3 -m portal.modules.security.core capability {list,query,tools,arsenal}`

## Goal-Driven Decide (Stage 2 — dry-run/proposal only)

Upgrades decide from lookup to reasoning. Deliberately stops at proposal + dry-run.

- `goal.py` — `EngagementGoal` + `validate_goal()`
- `goal_decide.py` — `decide_next_action()` over platform-core
- `loop.py::run_goal_engagement()` — open-ended loop, dry-run only
- `goal_eval.py::eval_proposals()` — Stage-3 go/no-go evidence

## Emergent Objective Loop (flag-gated)

Second path onto `portal.platform.agent.loop.run_loop`. Drops seeded first-move.

- `perception.py` — `LabPerception` hard-scoped to `10.10.11.0/24`
- `objective_executor.py` — `SecurityExecutor` wrapping real actuation
- `objective_entry.py` — `PORTAL_EMERGENT`-gated entry

## Drift-Detection Gate

Rolling-baseline regression + model-behavior canary. FLAG only.

- `drift_gate.py::drift_check(window=7)` — per (scenario, blue_model) pair
- `drift_gate.py::run_canary_probe(model)` — 12-probe deterministic suite

## Loop Notifications

Reuses existing notification subsystem. Fire-and-forget, non-fatal.

- Event types: `ENGAGEMENT_ESCALATED`, `ENGAGEMENT_STUCK`, `ENGAGEMENT_COMPLETE`
- Checkpoint/resume: `_write_checkpoint` persists `EngagementState`

## Why

Each sub-component extends the bench without touching the core chain: the capability index gives a decide step something legible to query, the goal-driven and emergent loops layer reasoning on top, drift gate flags model regressions across runs, and loop notifications surface long-running engagements. The deliberate pattern is containment — the capability index is read-only, goal decide stops at proposal, the emergent loop is flag-gated, and drift is a flag, not a verdict.
