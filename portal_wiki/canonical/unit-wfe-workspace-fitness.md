---
id: unit-wfe-workspace-fitness
kind: mixed
title: "Workspace Fitness Evaluation (WFE) — real-use fleet validation harness"
sources:
- type: code
  path: tests/wfe/settings_audit.py
- type: code
  path: tests/wfe/runner.py
- type: code
  path: tests/wfe/**/*.py
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

The harness (`tests/wfe/`):

- `settings_audit.py` — zero-model-call verification of every
  workspace/persona/council-seat placement: installed, backends-registered,
  baked num_ctx vs declared context_limit (Ollama /v1 ignores request-time
  options.num_ctx), sampling vs lane policy, tool-flag vs declared tools.
  Catches the glm_coder-128K class of silent regressions; the -ctxNk tag claim
  is verified against baked num_ctx rather than trusted; absent sampling in a
  deterministic lane is a FAIL; LANE_SAMPLING covers every live module.
- `runner.py` — multi-turn tool loop (file_read/file_list/repo_search/
  pytest_run/file_write/http_get, sandboxed per (task, repeat)) against the
  production `/v1` contract: tool-call arguments are a JSON string, normalised
  at the boundary; tool results carry tool_call_id. Deterministic persona
  resolution; token/latency economics captured; `--preflight` self-test.
- `schema.py` — outcomes are an enum, not a boolean; instrument failures
  (TOOL_ERROR/HARNESS_ERROR/BLOCKED) are quarantined out of every quality rate.
- `checkers.py` — extracted, unit-tested checkers (hidden_pytest against a
  model-unwritable graded suite, immutable, sandbox-only file_exists/
  file_contains, answer_contains with tool-output leak detection, cited_answer
  fetch-grounded, human_review → PENDING_REVIEW).
- `campaign.py` + `scripts/wfe_campaign.sh` — one-arm-per-process campaign
  driver with `--debug-dir` full-run capture and `--rescore` offline re-grade;
  `report.py` — deterministic Wilson-interval report, NOT SEPARATED not ranked.
- `dimensions.yaml` — the 28-dimension coverage contract report.py reads.
- `tools/build_compliance_suite.py` — regenerates compliance_agentic gold-
  stripped so the answer key cannot reach the model. `graded/` — hidden suites.
- Suites under `tests/wfe/suites/`, workload map `tests/wfe/workloads.yaml`,
  results `tests/wfe/results/`, checker/contract regression tests
  `tests/wfe/tests/`.

Governing task: docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md. Removals across the
fleet are HELD until its register v4. Gate: settings audit exits 0 FAIL at
Phase 0; fitness matrix drives disposition decisions.
