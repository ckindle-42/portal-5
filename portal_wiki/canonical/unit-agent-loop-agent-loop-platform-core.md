---
id: unit-agent-loop-agent-loop-platform-core
kind: what
title: "AGENT_LOOP \u2014 Agent Loop (platform core)"
sources:
- type: code
  path: portal/platform/agent/__init__.py
- type: code
  path: portal/platform/agent/goal.py
- type: code
  path: portal/platform/agent/interfaces.py
- type: code
  path: portal/platform/agent/decide.py
- type: code
  path: portal/platform/agent/rank.py
- type: code
  path: portal/platform/agent/loop.py
- type: code
  path: portal/platform/agent/writeback.py
- type: code
  path: portal/platform/agent/tests/test_agent_core.py
- type: code
  path: scripts/validate_system.py
last_generated_commit: 6afb262648d307376dfb4f839eeed69c02112d04
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.4984078
updated_at: 1784946220.4984078
---

`portal/platform/agent/` is the discipline-agnostic agent loop: a bounded,
grounded, writeback-capable engine that any module drives with its own action
space. It is **platform core** — always present, never a toggleable module;
validate check `AO` imports the package and enforces the inversion guard that
no file under it may import `portal.modules.*`.

- `goal.py` rejects execution without explicit scope (`scope.targets`) and
  iteration, wall-clock, and lab-action budgets (`max_iterations`,
  `max_wall_clock_sec`, `max_lab_actions`).
- `interfaces.py` defines structural capability-provider and executor contracts,
  keeping platform core independent of `portal.modules.*`.
- `decide.py` retrieves grounded candidates before choosing an action;
  `rank.py` supplies the deterministic tool and parameter fallback.
- `loop.py` enforces budgets, stop conditions, confidence gates, and honest
  blocked outcomes while folding each executor result into observations.
- `writeback.py` can propose a cited wiki unit, but never confirms or merges it.
- `portal/platform/agent/tests/test_agent_core.py` exercises those contracts
  hermetically without a live pipeline or network.

## Why

The loop is extracted to platform core so modules never reimplement
goal/decide/rank mechanics and never couple the engine to any module's
capability model. Keeping the package free of `portal.modules.*` imports is
what makes a single engine safe for every module at once — each module
implements the structural contracts and plugs in, which is exactly the
dependency-inversion relationship the AO guard exists to protect.
