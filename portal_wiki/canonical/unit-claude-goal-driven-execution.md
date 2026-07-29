---
id: unit-claude-goal-driven-execution
kind: why
title: "CLAUDE.md \u2014 Goal-Driven Execution"
sources:
- type: design
  path: CLAUDE.md
  section: Goal-Driven Execution
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1785348301.1943161
updated_at: 1785348301.1943161
---


**Define success criteria. Loop until verified.**

- Transform tasks into verifiable goals before coding: "fix the bug" → "write a test that reproduces it, then make it pass"; "refactor X" → "tests pass before and after".
- For multi-step tasks, state a brief plan with a verification check per step.
- The verification ladder is already fixed by this project — per-commit gate (`pytest tests/unit/ -q && ruff check . && ruff format --check .`), final gate (`bash scripts/ci_local.sh`), live streaming gate where required (`./scripts/smoke_stream.sh`), and doc reconciliation (Rule 12). A task isn't done until the applicable gates are green.

---
