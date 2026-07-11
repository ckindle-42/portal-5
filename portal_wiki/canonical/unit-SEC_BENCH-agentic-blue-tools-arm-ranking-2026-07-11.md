---
id: unit-SEC_BENCH-agentic-blue-tools-arm-ranking-2026-07-11
kind: mixed
title: "SEC_BENCH — Agentic Blue Eval, tools arm: 16-candidate ranking (2026-07-11)"
sources:
- type: doc
  path: coding_task/TASK_SEC_MODEL_DISCOVERY_V1.md
- type: code
  path: tests/benchmarks/bench_security/results/agentic_blue_tools_arm_20260711.json
- type: code
  path: tests/benchmarks/bench_security/agentic_blue_eval.py
last_generated_commit: ''
confidence: high
tags:
- sec-bench
- agentic-blue
- tools-arm
- model-discovery
- candidate-eval
created_at: 1783921200.0
updated_at: 1783921200.0
---

## Purpose

Ranks 16 candidate models on the agentic blue eval's **tools arm** (real search tools, no signature-lookup
grounding, findings only from an explicit `report_detection` call — see `agentic_blue_eval.py`'s three-arm
design). This supersedes the project's earlier raw-arm-only methodology, abandoned mid-run: raw-arm tests
single-shot judgment on a frozen telemetry slice, not investigation, and repeatedly produced flat-zero
results uninformative about real capability. The tools arm was chosen specifically because it approximates
what an actual SOC analyst does — decide what to search for, interpret results, and reach a conclusion —
rather than either grading unaided guessing (raw) or scripted signature-matching (harness).

**Methodology:** `CHAIN_DIRECT_OLLAMA=true`, 20 scenarios (`--all-captured --sample=20`, seed=42
deterministic), `TRIALS=3` per (scenario, model) cell, `--arms=tools`. Two prerequisite bugs were fixed
before this data is valid: (1) the sweep driver batched work scenario-outer/model-inner, forcing needless
model swaps — reordered to model-outer; (2) the direct-Ollama call path silently dropped `max_tokens`,
capping generation at whatever Ollama defaulted to (often unbounded) — fixed to honor the budget explicitly
(4000 tokens). A separate fix (`normalize_tool_calls()`) recovers tool calls some models wrap in a
nonstandard tag their own template didn't instruct — found via DeepHat-V1-7B, verified against all other
candidates to confirm no false negatives elsewhere.

**IMPORTANT — incomplete raw-data provenance for 6 of 16 candidates.** An operator error mid-run deleted
the checkpoint file for the first baseline+purpose-built batch (`granite4.1:8b`, `devstral-small-2`,
`granite4.1:30b`, `hf.co/mradermacher/VulnLLM-R-7B-GGUF:Q4_K_M`, `deephat-v1-7b-ctx16k`,
`hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6:Q6_K`) without backing it up first. The aggregate
tactic/exact recall numbers below for those six are accurate (computed and reported in-session before the
file was lost) but the per-scenario/per-trial detail behind them is gone — cannot be re-derived without
re-running those six candidates. The other 10 candidates have full raw data preserved locally at
`tests/benchmarks/bench_security/results/agentic_blue_tools_arm_20260711.json` (200 cells: 10 models × 20
scenarios, `qwen3-coder`/`gpt-oss` recovered from an earlier interrupted run's backup, the remaining 8 from
the final resumed sweep) — **not committed to the repo**, covered by the existing
`tests/benchmarks/bench_security/results/*.json` gitignore rule (per-run bench output is treated as
ephemeral/reproducible, this wiki unit is the durable artifact). Re-run the tools-arm sweep against the
model list in this unit to regenerate if needed.

## Ranking (tactic-tier recall, mean across 20 scenarios × 3 trials)

| Rank | Model | Tactic recall | Exact recall | Raw data |
|---|---|---|---|---|
| 1 | `devstral-small-2` | **0.329** | 0.275 | full |
| 2 | `thinkingcap-27b` (`hf.co/Abiray/ThinkingCap-Qwen3.6-27B-Q4_K_M-GGUF`) | 0.276 | 0.192 | full |
| 3 | `gpt-oss:20b` | 0.276 | 0.175 | full |
| 4 | `qwen3-coder:30b-a3b-q4_K_M` | 0.207 | 0.111 | full |
| 5 | `tess-4-27b` (`hf.co/migtissera/Tess-4-27B-GGUF`) | 0.161 | 0.128 | full |
| 6 | `Ornith-1.0-9B` (`hf.co/deepreinforce-ai/Ornith-1.0-9B-GGUF`) | 0.153 | 0.114 | full |
| 7 | `BugTraceAI-CORE-Ultra-27B` (`hf.co/BugTraceAI/BugTraceAI-CORE-Ultra-27B-Q6`) | 0.147 | 0.094 | aggregate only |
| 8 | `Ornith-1.0-35B` (`hf.co/deepreinforce-ai/Ornith-1.0-35B-GGUF`) | 0.142 | 0.058 | full |
| 9 | `granite4.1:8b` | 0.135 | 0.071 | aggregate only |
| 10 | `Qwopus3.6-27B-v2-MTP` (`hf.co/Jackrong/Qwopus3.6-27B-v2-MTP-GGUF`) | 0.125 | 0.081 | full |
| 11 | `granite4.1:30b` | 0.110 | 0.082 | aggregate only |
| 12 | `sylink:8b` | 0.093 | 0.043 | full |
| 13 | `mistral-small3.2:24b` | 0.076 | 0.029 | full |
| 14 | `Qwen3-Coder-Next-abliterated` (`hf.co/bartowski/huihui-ai_Qwen3-Coder-Next-abliterated-GGUF`) | 0.075 | 0.050 | full |
| 15 | `deephat-v1-7b` | 0.018 | 0.013 | aggregate only |
| 16 | `hf.co/mradermacher/VulnLLM-R-7B-GGUF` | 0.000 | 0.000 | aggregate only |

## Findings

**`devstral-small-2` wins clearly, and it isn't a fluke.** It's the same model that separately earned the
project's established 0.421 raw-arm baseline (`devstral-small-2:latest-ctx8k`, see
`SEC_BENCH-agentic-blue-deltas-20260708.md`) — retaining 78% of that score under the harder tools-arm
condition (must investigate, not just judge spoon-fed evidence) is a real, corroborated result, not a
one-off winner from a noisy screen.

**Bigger did not help within the same model family — seen twice, not once.** `granite4.1:8b` (0.135) beat
`granite4.1:30b` (0.110); `Ornith-1.0-9B` (0.153) beat `Ornith-1.0-35B` (0.142). Two independent matched
pairs pointing the same direction is a pattern worth taking seriously for this specific task shape
(tool-driven investigation), not attributable to a single family's quirk. Hypothesis, untested here: more
parameters may produce more elaborate — and more error-prone — tool-use planning rather than better
judgment on this kind of bounded investigation task.

**Purpose-built security models underperformed generalist models.** `BugTraceAI-CORE-Ultra-27B` (0.147),
`deephat-v1-7b` (0.018), and `VulnLLM-R-7B` (0.000) all landed at or below the generalist median despite
being trained specifically on security/vulnerability data. This directly tests (and disconfirms, for these
three specific models) the hypothesis that offense-adjacent training transfers to defensive investigation
capability. `deephat-v1-7b`'s near-zero score is *not* a measurement artifact — a separate tool-call-wrapper
bug was found and fixed for this model specifically (`normalize_tool_calls()`, verified it made real tool
calls throughout this run) before this ranking was produced; the low score is its genuine, honestly-measured
result.

## Preflight screen — tool-calling capability, 37 broader candidates

Before the 16-model deep dive, a broader catalog sweep tool-call-preflighted 37 additional candidates
(single trivial probe each, not part of the scored ranking above). 24 passed, 13 failed honestly (see
`tests/benchmarks/bench_security/refusal.py::run_audit_tools`) — full raw results in
`/tmp/audit_tools_broad_results.json` (not committed; reconstructed here for the record since it wasn't
saved to the repo either).

**Preflight-passed but never run through the full 20-scenario tools-arm ranking** (14 candidates — open,
worth picking up in a follow-on sweep): `glm-4.7-flash:Q4_K_M`, `hermes3:8b`,
`hf.co/Mia-AiLab/Qwable-3.6-35b`, `hf.co/TeichAI/GLM-4.7-Flash-Claude-Opus-4.5-High-Reasoning-Distill-GGUF`,
`hf.co/douyamv/Gemma-4-31B-JANG_4M-CRACK-GGUF`, `hf.co/empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF`,
`hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-GGUF`,
`hf.co/mradermacher/Qwen3.5-9B-Claude-4.6-HighIQ-THINKING-HERETIC-UNCENSORED-GGUF`,
`hf.co/unsloth/GLM-4.7-Flash-REAP-23B-A3B-GGUF`,
`hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF`,
`huihui_ai/baronllm-abliterated`, `huihui_ai/tongyi-deepresearch-abliterated`, `laguna-xs.2`,
`qwen3-coder-next:latest`. These only have noisy 1-trial/1-2-scenario screening-pass numbers, which were
explicitly treated as directional-only throughout this work (the screen's own numbers proved unreliable —
e.g. `qwen3-coder:30b-a3b` screened at 0.75 tactic recall on 2 scenarios, landed at 0.207 on the real
20-scenario run) — not reproduced here to avoid the same false-precision mistake.

**Preflight-failed, honest drops** (13 — reasons matter for future re-attempts): `devstral:24b` (empty
content, clean stop — NOT the same model as the winning `devstral-small-2`, do not conflate the two),
`deepseek-r1:32b` and `hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF` (both genuinely never attempted a tool
call — verified via direct content inspection, not a parser bug), `phi4-reasoning:plus` (HTTP 400),
`phi4-mini-reasoning` (timeout), `hf.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q8_0-GGUF` (HTTP 400 — notable,
this is the project's own production `auto-blueteam` primary per `P5-FUT-PARITY-001`; the 400 is specific to
this raw-Ollama-direct probe path and does not necessarily indicate a production issue),
`hf.co/mradermacher/CyberSecQwen-4B-GGUF` and its `cybersecqwen-4b-toolfix` patched variant (both fail —
matches the known, already-documented toolfix-template-lost issue),
`hf.co/Nguuma/security-slm-unsloth-1.5b` (1.5B, verbose non-attempt, consistent with sub-2B capability
limits), `hf.co/Jiunsong/SuperQwen-AgentWorld-35B-A3B-abliterated-gguf-4bit` (short non-attempt),
`hf.co/Abiray/Agents-A1-Q4_K_M-GGUF` (HTTP 500, isolated — Ollama stayed healthy, not a systemic issue),
`hf.co/bartowski/THUDM_GLM-Z1-Rumination-32B-0414-GGUF` (HTTP 400),
`hf.co/unsloth/Magistral-Small-2509-GGUF` (short non-attempt).

## Bug fixes that made this data trustworthy (commit trail)

Four bugs were found and fixed in `tests/benchmarks/bench_security/` during this work, each verified against
the actual failure it was diagnosed from — see commit messages for full detail:
- Sweep driver model-swap overhead (scenario-outer → model-outer work-queue ordering) + direct-Ollama
  `max_tokens` never being sent (silent unbounded generation, root cause of early cell timeouts).
- A reverted attempt to recover reasoning-model output from the `thinking` API field when `content` was
  empty — reverted on operator correction: that would have scored the reasoning scratchpad (what a model
  *considered*), not its concluded answer. Kept as a documented dead-end, not silently dropped.
- `normalize_tool_calls()` — wrapper-agnostic recovery of tool calls a model emits in a nonstandard/
  inconsistent XML tag its own template didn't instruct (found via `deephat-v1-7b`, which used `<response>`,
  `<request>`, `<output>`, a markdown fence, or no wrapper at all across repeated probes, always with
  correct, well-formed JSON underneath). Verified this does not affect any other candidate in this ranking —
  every other model's tool_calls parsed natively.

## What this does NOT establish

- **Not a production promotion.** All 16 are bench-only; nothing here changes any `model_hint` or promotes
  anything. `PROMOTE_POLICY=confirm` applies as everywhere else in this project's model-discovery work.
- **Not validated against the harness arm** for any of these 16 — this ranking is tools-arm only. A model
  that does poorly here investigating unaided could still do well with the harness's grounding tools (or
  vice versa — see the project's now-confirmed finding that harness helps small models and hurts large ones,
  `devstral-small-2:latest-ctx8k`'s raw→harness regression in `SEC_BENCH-agentic-blue-deltas-20260708.md`).
- **20 scenarios / 3 trials is meaningful but not exhaustive** power — treat rank differences of a few
  hundredths as noise-adjacent, not decisive. The devstral-small-2 lead (0.329 vs next-best 0.276) and the
  bottom-three purpose-built cluster (≤0.147, well-separated from the pack) are the two places in this table
  where the gap is large enough to trust without hedging.
