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
- type: code
  path: tests/_netguard/*.py
- type: code
  path: tests/wfe/prompt_surface.py
- type: doc
  path: docs/TASK_WORKSPACE_FITNESS_EVAL_V1.md
claims: []
confidence: high
tags:
- authored-v1
- tests
- evaluation
created_at: 1788792773.476087
updated_at: 1792321100
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
- Timing economics keep `prefill_s`, `ttft_s`, reasoning and visible-answer
  counts and durations, `answer_tps`, `tool_s`, `total_s`, `timing_source`, raw
  `reasoning_deltas` / `answer_deltas`, phase character counts, and `split_source`
  on each turn and row. A delta count is one nonempty stream frame, not a tokenizer
  token count. When an engine supplies only an aggregate completion count, the
  pipeline apportions it by reasoning/answer delta counts, falling back to the
  phase character counts when deltas are unavailable. Without an engine count,
  measured delta counts remain estimates. Row economics roll up durations and
  counts, retain the first TTFT and recompute answer TPS. The report repairs old
  rows without `split_source` from reasoning and final-answer character counts,
  and shows median and nearest-rank p90 answer TPS, decode TPS
  (`completion_tokens / (reasoning_s + answer_s)`), TTFT and model total time
  per workspace, lane and arm.
- Pipeline mode (`WFE_ENGINE=pipeline`, source `.env` for `PIPELINE_API_KEY`) is
  the standard path for seat testing: every request goes to the Portal pipeline
  (`:9099`) under the workspace id, as Open WebUI sends it. The pipeline applies
  seat sampling, `think`, the prompt append, routing and tool-call recovery.
  Only an arm's explicit override is sent (caller wins key by key). Requests
  carry `portal_client_tools_only`, so the seat is measured on the harness
  toolset and calls come back to the harness. Each request's pipeline trace
  (`/v1/trace/{id}`) confirms the served model: preflight refuses an arm the
  pipeline would route elsewhere, and a row served by another model is BLOCKED.
  Direct engine modes stay for raw model and engine probes.
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
  `sweep_plan.py` — writes `plans/sweep_from_queue_v1.yaml` from the candidate
  queue's intended workspaces and the incumbents in `plans/*_decision_v1.yaml`.
  A queued model is a challenger only where `workspace_routing` serves it and
  its `ctxNk` window is at least that workspace's `context_limit`.
- `scripts/wfe_supervise.py` — the watcher that makes a long sweep cheap to
  leave alone. `run_arm`'s auto-halt stops one arm whose task kind has gone bad,
  but the driver then starts the next arm, so a sweep can halt arm by arm and
  still reach its end unread. The supervisor polls `campaign.health()` plus
  cross-arm tripwires every five minutes and EXITS on the first problem — a new
  `arm_exits.log` HALT, a cell at or below 10% PASS over 12+ graded rows, a cell
  where 90%+ of tool-offered rows called no tool, or 25%+ of a cell's rows
  carrying a spoiled answer (zero-width garbling, raw `<tool_call>` markup, a
  download link answering a read task, a PASS on almost no text). Run detached,
  its exit is the signal to come and look. `--sample N` prints the newest rows
  with their answers and smells: the automatic checks cover the failures already
  seen, and reading the answers covers the one that matters most — a run that is
  healthy by every exit code and producing evidence nobody can use.
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

## Measurement caveats (added 2026-10-12)

- **Prompt/tool-surface mismatch (fixed 2026-10-12; seat baseline V2).**
  Persona prompts and `system_prompt_append` name production tools the harness
  does not offer (auto-compliance: `nerc_cip_requirement`, `compliance_ask`, …),
  and auto-compliance's output taxonomy conflicted with the suite's JSON labels.
  `workspace_context` appends the `WFE HARNESS TOOLS:` note from
  `tests/wfe/prompt_surface.py`, naming the six-tool proxy surface and giving the
  user turn's output format precedence. Until 2026-10-12 pipeline mode sent
  `system_prompt_base` without the note, so the fix only reached direct-engine
  runs; `system_prompt_pipeline` now carries it. `wfe_prompt_surface_rebaseline_20261012`
  (direct Ollama, 87 rows) is a direct-engine measurement, not the seat baseline;
  its "zero warnings" receipt was vacuous (the audit skipped any prompt carrying
  the note and never read user turns — it now flags a task demanding a tool the
  surface lacks). A task that needs a production tool declares `requires_tools`
  and is BLOCKED (comp-reading-contract-01). A FAIL that carries the task's
  completion signal is no longer relabelled REFUSED. V1 corrections in
  `docs/WFE_PROMPT_SURFACE_REBASELINE_V1.CLOSEOUT.md`.
- **Seat baseline (pending: TASK_WFE_PROMPT_SURFACE_REBASELINE_V3).**
  `wfe_prompt_surface_seat_20261012` (V2) is NOT a seat baseline: 19 of its 30
  auto-compliance rows ran on the Ollama failover, not the oMLX alias seat. Its
  "seat × think-off × format-clause" loop attribution compared different tasks
  across engines and is withdrawn. Corrections, and the instrument defects that
  fed its loops and FAILs, are in `docs/WFE_PROMPT_SURFACE_REBASELINE_V2.CLOSEOUT.md`.
  Defects: `repo_search` ignoring a file path, packet tasks reading the repo, an
  unmapped `/workspace`, the pipeline no-answer placeholder scored as an answer,
  and the code-kv escape mismatch. Pipeline-mode rows now count only when
  every model turn is served by the seat's primary model (`seat_primary`).
- **Instrument audit (2026-10-13): pre-audit WFE and probe numbers are biased.**
  `docs/WFE_INSTRUMENT_AUDIT_20261013.md` lists 19 defects and the dispositions
  resting on them. In short:
  - Workspaces were measured with an arbitrary persona prompt; they now use the
    workspace's own `owui_system_prompt`.
  - Challengers ran at the incumbent's sampling; they now run at their card's.
  - Compliance was graded on ambiguous, internally inconsistent exact labels; it
    is now graded by violation class.
  - Silent Ollama context truncation went undetected; it is now
    `evidence.context_overflow`.
  - The judgment probe ran think-off at 700 tokens; it now uses the council
    transport.
  - Domain probes scored empty answers as wrong, or scored the model's
    reasoning text.

  By class re-grade, the auto-compliance incumbent ties granite4.1:30b
  (24/30 each). Treat every WFE/probe rate before 2026-10-13 as "pre-audit".
- **Root fixes (2026-10-13, in progress).** `docs/WFE_ROOT_CAUSES_20261013.md`
  consolidates both audits into the root causes C1–C6 and specifies their fixes:
  C1 two measurement paths, C2 checkers never shown to work, C3 decisions record
  nothing of what measured them, C4 samples too small and an ambiguous decision
  rule, C5 unit tests reach live services, C6 the jobs are not covered.
  `WFE_ROOT_FIX_PROGRAM.md` splits the work into five parts, and
  `docs/WFE_ROOT_FIX_ACCEPTANCE.md` is its acceptance ledger. The decision rule
  lives only in `tests/wfe/decision.py`, known-answer controls only in
  `tests/wfe/controls.py`, and the unit-test offline boundary only in
  `tests/_netguard/netguard.py`. Probe evidence stays diagnostic: no probe is
  decision-grade, and only pipeline-mode WFE rows can set a seat or a disposition.
- **Identity, ledger and check HP (P1R, 2026-10-14).** The build that served each
  (workspace, model) is observed in the engine's own store (the Ollama manifest
  digest; for oMLX the checkpoint's config, tokenizer, template, weight-file sizes and
  model_settings entry), frozen at every arm's preflight and re-checked after every
  row: a change blocks the arm or quarantines the row. A build that cannot be
  observed blocks the arm. `report --record` writes both sides' identity and the
  incumbent into `tests/wfe/fitness_ledger.yaml`; check HP reads seats from
  portal.yaml's `model_hint` and flags a cell STALE when production now serves a
  different model or different content. The backfill decides restorability by asking
  the registry and comparing digests. Spec: `docs/WFE_ROOT_CAUSES_20261013.md`.
- **Card-think arms.** A model whose card reasons (think on by default) must
  ALSO be measured at its card think + sampling setting, not only at the lane's
  forced think-off policy. Report both, and attribute "lane fit" (the lane's
  think-off policy plus its output-format clause) separately from "model
  capability". The Saluki re-verify showed the two can differ: the same model
  looped under think-off and answered under think-on.
- **Answer-key isolation.** The sandbox must never expose the suite files or
  `tests/compliance_probe/` or committed WFE receipts through `file_read` or
  `repo_search`; `REPO_DENY_PREFIXES` in `tests/wfe/runner.py` enforces this
  (regression: `tests/wfe/tests/test_wfe_gold_isolation.py`).
- **Loop attribution.** Before naming a model as the cause of a turn-cap loop,
  follow the protocol in [[unit-wfe-loop-attribution-protocol]].


## Production tool mode: the row's own trace

In production tool mode the pipeline, not the harness, dispatches the workspace's
tools, so a row asks for `exec_audit` and reads the pipeline's audit event (tool,
arguments, output for every dispatched call, also at the hop limit) as its tool
log. The `tool_grounded` checker passes only when a successful call to an allowed
tool returned every evidence pattern; an output that reports a failure
(`resolved`, `found` or `success` false, or an `error` field) never grounds an
answer, even when it echoes the id that was asked for. The compliance and data
production suites (`compliance_production`, `data_production`) are graded this way.

Phase C ran both suites end to end (compliance `wfe_compliance_decision_20261016*`, data
`wfe_data_decision_20261016*`; decisions in `docs/WFE_DECISION_AUTO_*_CFIX_20261016.md`). What it taught the
instrument: an arm id can carry a variant label (`<tag>@<label>-<digest>`), which the candidate queue and the
fitness report match by the bare tag; a determination task is attainable only when every fact its gold needs is
reachable through the tools (`tests/wfe/e2e/compliance_attainability.py` proves that against the evaluation
store, which now captures and anchors the register's standards); and an instruction may enumerate only values
it defines. A seat's sampling is judged against its build provider's guidance (Unsloth first, then the vendor
card): `settings_audit` fails a production seat that differs unless its `sampling_override` carries a reason and
measured evidence. A tool-using model that re-issues an identical call is answered from the earlier result and,
on a third repeat, finishes without tools; a workspace flagged `require_tool_before_answer` (auto-data) retries
once when a turn answers with no tool call.

The compliance evaluation store (`compliance-mcp-eval`) is built from the committed
planted corpus with each document's answer-key header stripped. Each document is
registered, captured and projected under its own id, because the retrieval index is
a projection of the canonical section store: an embed-only ingest leaves
`compliance_read` unable to resolve the id. The build fails when nothing captures.

A prompt longer than the served `-ctxNk` tag is detected by the pipeline when the
engine reports fewer prompt tokens than were sent (trace note `prompt_truncated`,
the `prompt_truncated` error counter, a one-line notice); a runner that refuses it
with HTTP 400 is recorded by the harness as `context_overflow`.
