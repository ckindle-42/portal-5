---
id: unit-wfe-workspace-fitness
kind: mixed
title: "Workspace Fitness Evaluation (WFE) — real-use fleet validation harness"
sources:
- type: code
  path: tests/wfe/settings_audit.py
- type: code
  path: tests/wfe/runner.py
- type: doc
  path: docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md
claims: []
confidence: high
tags:
- authored-v1
- tests
- evaluation
created_at: 1788792773.476087
updated_at: 1788792773.476087
---

The WFE harness evaluates a model IN its workspace context — persona system
prompt, declared tools, multi-turn — on real checkable work, because
short-prompt instruments cannot diagnose real usability (operator doctrine
2026-09-07; see docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md).

## Why

Two surfaces, one per file:

- `tests/wfe/settings_audit.py` — zero-model-call verification of every
  workspace/persona/council-seat placement: installed, backends-registered,
  baked num_ctx vs declared context_limit (Ollama /v1 ignores request-time
  options.num_ctx), sampling vs lane policy, tool-flag vs declared tools.
  Catches the glm_coder-128K class of silent regressions.
- `tests/wfe/runner.py` — multi-turn tool loop (file_read/file_list/
  repo_search/pytest_run/file_write/http_get, sandboxed to the task root)
  with objective checkers (pytest_pass, file_exists, file_contains,
  transcript_contains, human_review). Suites under tests/wfe/suites/,
  workload map tests/wfe/workloads.yaml, results tests/wfe/results/.

Governing task: docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md. Removals across the
fleet are HELD until its register v4. Gate: settings audit exits 0 FAIL at
Phase 0; fitness matrix drives disposition decisions.
