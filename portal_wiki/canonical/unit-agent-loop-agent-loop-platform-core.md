---
id: unit-agent-loop-agent-loop-platform-core
kind: what
title: "AGENT_LOOP \u2014 Agent Loop (platform core)"
sources:
- type: doc
  path: docs/AGENT_LOOP.md
  commit: 05e42ec2
  section: Agent Loop (platform core)
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
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.4984078
updated_at: 1784946220.4984078
---

`portal/platform/agent/` is the discipline-agnostic agent loop: a bounded,
grounded, writeback-capable engine that any module drives with its own action
space. It is **platform core** — always present, never a toggleable module.

- `goal.py` rejects execution without explicit scope and iteration, wall-clock,
  and lab-action budgets.
- `interfaces.py` defines structural capability-provider and executor contracts,
  keeping platform core independent of `portal.modules.*`.
- `decide.py` retrieves grounded candidates before choosing an action;
  `rank.py` supplies the deterministic tool and parameter fallback.
- `loop.py` enforces budgets, stop conditions, confidence gates, and honest
  blocked outcomes while folding each executor result into observations.
- `writeback.py` can propose a cited wiki unit, but never confirms or merges it.
- `tests/test_agent_core.py` exercises those contracts hermetically without a
  live pipeline or network.
