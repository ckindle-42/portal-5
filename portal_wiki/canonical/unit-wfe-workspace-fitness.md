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
  is verified against baked num_ctx rather than trusted.
  `--behavioral` adds per-tag template probes that DO call the model:
  system-instruction honored, clean JSON under `format: json`,
  `template_tools_ignored` (a real `tools` array and a question only a tool call
  can answer — prose with no `tool_calls` is a FAIL, which is how a
  `tool_trace=[]` stops being a mystery about the model and becomes a
  measurement of the template), and `template_think_ignored` (`think: true` then
  `think: false`; honored means `message.thinking` non-empty then empty, and an
  HTTP 400 is recorded as REFUSED rather than confused with a silently ignored
  flag). Every probe sends `think: false` explicitly — omitting the key leaves
  the template in charge, and on a reasoning-family template a 20-token probe
  budget goes entirely to `thinking`, which made the system-instruction probe
  FAIL correct templates. `--tag <tag>` probes one seat instead of sweeping
  every workspace incumbent, and returns the verdicts a campaign pins. The sampling check
  compares the temperature the PIPELINE serves — `effective_temperature`:
  think-profile → workspace flat field → baked tag → Ollama default, mirroring
  router/validation.py — against the lane ceiling, not the baked tag value in
  isolation; a cool workspace over a hot tag is a `sampling_baked_hot` WARN, not
  a FAIL. `eval` is instrumentation and is checked non-deterministically at the
  stock default.
- `compliance_preflight.py` — the REQUEST path, which `settings_audit` (config
  and metadata) makes no promises about. Per candidate seat: the behavioural
  probes, then one real call carrying the first-turn thread for the largest
  CIP-007-6 population, with every number read back from the runner — applied
  `num_ctx` from `/api/ps`, `prompt_eval_count`, headroom, observed
  chars-per-token, template sha, baked params, `ollama ps`, free memory — and a
  go/no-go. It exists because a baked `num_ctx` is a DEFAULT, not a ceiling:
  native `/api/chat` honours a larger request-time value (measured: a 32,768
  tag served 65,536) and refuses an oversized prompt with HTTP 400
  `exceed_context_size_error` rather than truncating it, so what a path
  actually gets has to be measured, not read off the tag name.
- `runner.py` — multi-turn tool loop (file_read/file_list/repo_search/
  pytest_run/file_write/http_get, sandboxed per (task, repeat)) against the
  production `/v1` contract: tool-call arguments are a JSON string, normalised
  at the boundary; tool results carry tool_call_id. Every request is STREAMED on
  the wire and a STALL — no bytes for STALL_S (default 300, `WFE_STALL_S`) —
  aborts the turn as `BUDGET_EXHAUSTED`, never a blind total-time cap: a
  slow-but-progressing model keeps its work and logs progress, a wedged backend
  is caught in minutes. Deterministic persona resolution; token/latency
  economics captured; `--preflight` self-test reconciles observed strict-JSON
  behaviour (empty OR degenerate) against the model card's format_json_safe.
- Engine mode (`WFE_ENGINE`, `WFE_CHAT_BASE_URL`) — points the same campaign
  at any OpenAI-compatible engine (oMLX, mlx-serve, Rapid-MLX, vllm-mlx,
  mlx_lm.server) for an engine head-to-head. Ollama stays the model manager
  (draining it frees memory for the engine under test); preflight's native
  probes run on `/v1`; thinking goes through `chat_template_kwargs.enable_thinking`
  instead of Ollama-only fields; the engine is stamped into the environment
  fingerprint only when set, so existing Ollama campaigns keep theirs and can
  never be mixed with an engine campaign. Unset, behaviour is unchanged. The
  companion speed/security harness was archived 2026-09-24 to
  `scripts/_archive/engine_h2h_20260924/` (docs/MIMO_V26_DISTILL_9B_BRINGUP_V1.md).
- Every sampling key the workspace resolves (temperature, top_p, top_k, min_p,
  repeat_penalty, presence_penalty, seed) is sent on both `/v1` and `/api`
  (`SAMPLING_KEYS`). Before 2026-09-24 only temperature/top_p/seed were, and
  non-Ollama engines ran without the workspace's loop guard.
- `schema.py` — outcomes are an enum, not a boolean; instrument failures
  (TOOL_ERROR/HARNESS_ERROR/BLOCKED) are quarantined out of every quality rate.
- `checkers.py` — extracted, unit-tested checkers (hidden_pytest against a
  model-unwritable graded suite, immutable, sandbox-only file_exists/
  file_contains, answer_contains with tool-output leak detection, cited_answer
  fetch-grounded, human_review → PENDING_REVIEW).
- `compliance_reading_contract` scores the reading contract from what was
  OBSERVED: the transcript's own `tool_calls` and the receipt `compliance_ask`
  returned, never the JSON object a model writes about its own run. Three ways
  it previously reported a false PASS, each now a regression lock in
  `tests/wfe/tests/`: `closure_complete is (not unread)` is TRUE when the model
  reports `false` with a non-empty unread list, so an explicitly incomplete
  closure passed as a satisfied one; citations were only scanned for
  `resolved is not True`, so an empty citation list passed every time; and
  `first_tool` was whatever the model said it was, with `ctx.tool_calls` never
  read, so a run with no tool calls at all could pass. Ground-truth recall binds
  to the evaluation set (the APPROVED mappings) through
  `ground_truth_requirement`; with no labels the outcome is PENDING_REVIEW —
  honest-BLOCKED, never a pass, because a gate that passed against nothing would
  qualify a seat against nothing.
- `campaign.py` + `scripts/wfe_campaign.sh` — one-arm-per-process campaign
  driver with `--debug-dir` full-run capture and `--rescore` offline re-grade;
  `--preflight` probes every arm before the sweep, and each arm releases its
  model (`keep_alive: 0`) so co-resident weight never becomes the measurement;
  `report.py` — deterministic Wilson-interval report, NOT SEPARATED not ranked.
- `scripts/wfe_sweep_unattended.sh` — the unattended kickoff. The sweep talks
  straight to Ollama, so the Portal stack is not a dependency but a competitor
  for memory: this stops it for the duration, evicts every resident model,
  preflights the roster, runs the sweep and restores the stack via trap.
- `dimensions.yaml` — the 28-dimension coverage contract report.py reads.
- `tools/build_compliance_suite.py` — regenerates compliance_agentic gold-
  stripped so the answer key cannot reach the model. `graded/` — hidden suites.
- Suites under `tests/wfe/suites/`, workload map `tests/wfe/workloads.yaml`,
  results `tests/wfe/results/`, checker/contract regression tests
  `tests/wfe/tests/`.

Governing task: docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md. Removals across the
fleet are HELD until its register v4. Gate: settings audit exits 0 FAIL at
Phase 0; fitness matrix drives disposition decisions.
