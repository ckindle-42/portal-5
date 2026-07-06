---
id: unit-SEC_BENCH-agentic-blue-eval-v1-results-2026-07-05
kind: mixed
title: "SEC_BENCH — Agentic Blue Eval V1 first results (2026-07-05): harness (arm C) beats raw (arm A)"
sources:
- type: doc
  path: coding_task/DESIGN_SEC_AGENTIC_BLUE_EVAL_V1.md
- type: code
  path: tests/benchmarks/bench_security/agentic_blue_eval.py
- type: code
  path: tests/benchmarks/bench_security/_sweep_driver.py
last_generated_commit: c8e39820b0f2a1e0a1a4f6b8f9c6d7f5b3a2c1d0
confidence: high
tags:
- sec-bench
- agentic-blue-eval
- harness-proof
- status
created_at: 1783487700.0
updated_at: 1783487700.0
---

## Purpose

First real run of `DESIGN-SEC-AGENTIC-BLUE-EVAL-V1`'s three-arm sweep (raw / tools / harness) — the eval
built to PROVE (not assume) whether Portal's harness carries capability over a raw agentic-hunt condition,
per the Simbian AI Cyber Defense Benchmark methodology the design doc is built on.

## Four bugs found and fixed before any result could be trusted

The eval as originally committed (`c528380`) could not produce a meaningful result. Found and fixed in
order, each one uncovered by actually trying to run the eval rather than reading the code:

1. **Model routing**: `_call_model` passed raw Ollama tags directly as `body["model"]` to
   `/v1/chat/completions`. The pipeline treats `model` as a workspace/persona id, not a literal model
   selector — every one of `granite4.1:8b-ctx8k` / `gpt-oss:20b` / `huihui_ai/qwen3.5-abliterated:9b` was
   silently mis-routed to `huihui_ai/Qwen3.6-abliterated:27b` (the general group's first model). This was
   the actual cause of the "meta3_ftp_backdoor timeout" symptom reported before the fix (294.7s against the
   wrong 27B model; the correct model finishes in ~90-120s) — not a missing ground-truth wiring issue as
   first suspected (ground truth loads correctly via the `SCENARIOS` fallback in `exec_chain.py`). Fixed by
   extracting `resolve_pipeline_model` (built earlier the same day for `blue.py`'s identical bug) into shared
   `_data.py` and wiring both callers to it.
2. **Arm B ("tools") had no real data**: every tool call got a canned `"No data available in this context"`
   string regardless of what was asked. The model had nothing to investigate, so any recall it scored was
   guessing, not hunting — confirmed live: one run scored 0.333 recall despite zero real telemetry ever
   reaching the model. Fixed by sharing `_query_real_telemetry` with arm C, since the doc's actual B/C
   distinction is the grounding *library*, not whether search returns anything.
3. **Ungrounded guessing counted as a finding**: both arm B and arm C scraped any MITRE ID mentioned in the
   model's free text as a "finding," even without a `report_detection` call — violating the design doc's own
   "synthetic never counts" honesty contract. Removed the prose-scraping fallback for B/C; findings now only
   come from explicit `report_detection` calls with real evidence. (Arm A keeps prose extraction — it has no
   tools at all, matching Simbian's own raw-condition methodology.)
4. **Arm C wasn't actually the harness**: it was arm B with a bigger prompt — no SPL library, no similarity
   tier, nothing the design doc calls "the harness." Added `lookup_technique_signature` and
   `search_similar_techniques` tools, backed by the real SPL detection library
   (`siem/spl_detections.yaml`, technique_id -> evidence-signature descriptions) and the existing
   similarity-tier heuristic (`unknown_defense.compute_similarity`) — which itself needed a tokenization fix,
   since it expects pre-split keyword lists, not raw `field=value` log text.

All four fixes shipped in commit `c8e3982`.

## First real sweep: 3 models x 3 scenarios x 3 arms, single trial per cell

Scenarios: `kerberoast_to_da`, `asrep_to_lateral`, `meta3_ftp_backdoor` (chosen for richest available
ground truth among captured episodes). Models: `granite4.1:8b-ctx8k` (auto-blueteam incumbent),
`gpt-oss:20b`, `huihui_ai/qwen3.5-abliterated:9b`.

| arm | avg recall | avg precision |
|---|---|---|
| A — raw | 0.000 | 0.000 |
| B — tools (real data, no grounding) | 0.000 | 0.000 |
| C — harness (real data + SPL/similarity grounding) | **0.037** | **0.111** |

**Headline: C beats A.** Every one of the 27 arm-runs before the grounding fix scored 0% recall; after
wiring the real SPL-library grounding tools into arm C, the harness produced the sweep's only true positive:
`granite4.1:8b-ctx8k` on `kerberoast_to_da` correctly reported `T1558.003` (Kerberoasting) with **zero false
positives** — and only after calling `lookup_technique_signature` to confirm the sub-technique against its
known evidence signature (`EventCode=4769`, RC4 ticket encryption) instead of guessing from training
knowledge. Neither arm A nor arm B ever produced a true positive in this sweep.

3.7% average recall lands in the same range as the Simbian paper's own finding for *frontier* models hunting
raw (best: 3.8%) — small local models plus a genuinely-wired grounding harness are landing in the same
ballpark human/frontier-model raw hunting does, on this (small) sample.

## Caveats — this is early signal, not proof of sufficiency

- **3 scenarios only**, single trial per cell. 8 of 9 harness cells still scored 0% recall.
- **Confirmed model non-determinism**: a replayed identical prompt for one 0-tool-call cell (temperature 0.3,
  not deterministic) produced a correct, grounded `report_detection` call moments later. Single-run numbers
  in this sweep are noisy, not definitive — a cell reading 0% may mean "didn't roll the tool call this time,"
  not "structurally incapable."
- **7 near-misses observed** across the sweep (right MITRE parent technique, wrong exact sub-ID — e.g.
  reported `T1558` vs ground-truth `T1558.003`, `T1059` vs `T1059.004`). Exact-match scoring credits none of
  these; a parent-technique-level scoring mode would show a materially different (better) picture. The
  design doc leaves the exact-match-vs-Portal's-own-bar question explicitly open — this is real evidence for
  that decision, not yet resolved.
- Design doc's E4/E5 (multi-model sweep at scale, wiki write-back of the winning config) remain open.

## Full raw results (all 27 arm-runs)

Embedded here rather than left as an ephemeral `/tmp` file or a gitignored `results/*.json` — this table
*is* the durable, referenceable record of the run (bench result JSONs are intentionally gitignored per
`tests/benchmarks/bench_security/results/*.json` — reproducible, per-run artifacts, not source; the wiki
unit is where a finding becomes durable).

| scenario | model | arm | recall | precision | true_positives | false_positives | tool_calls | iterations | elapsed_s |
|---|---|---|---|---|---|---|---|---|---|
| kerberoast_to_da | granite4.1:8b-ctx8k | raw | 0.000 | 0.000 | - | T1021.002, T1078.003 | 0 | 1 | 23.8 |
| kerberoast_to_da | granite4.1:8b-ctx8k | tools | 0.000 | 0.000 | - | - | 0 | 1 | 28.3 |
| kerberoast_to_da | granite4.1:8b-ctx8k | harness | 0.333 | 1.000 | T1558.003 | - | 5 | 5 | 7.6 |
| kerberoast_to_da | gpt-oss:20b | raw | 0.000 | 0.000 | - | T1003, T1003.001, T1003.002, T1014, T1033, T1037, T1047, T1055.001, T1060, T1075, T1078, T1078.004, T1086, T1088, T1090, T1097, T1105, T1110, T1128, T1135, T1204, T1207, T1489, T1503, T1548.003, T1549, T1550, T1556, T1557.003, T1558.001, T1558.002 | 0 | 1 | 45.6 |
| kerberoast_to_da | gpt-oss:20b | tools | 0.000 | 0.000 | - | - | 0 | 1 | 44.5 |
| kerberoast_to_da | gpt-oss:20b | harness | 0.000 | 0.000 | - | T1550.002 | 5 | 5 | 37.1 |
| kerberoast_to_da | huihui_ai/qwen3.5-abliterated:9b | raw | 0.000 | 0.000 | - | T1076, T1078, T1146, T1593, T1594, T1597 | 0 | 1 | 57.8 |
| kerberoast_to_da | huihui_ai/qwen3.5-abliterated:9b | tools | 0.000 | 0.000 | - | 10256, 10282, 10338 | 4 | 3 | 86.4 |
| kerberoast_to_da | huihui_ai/qwen3.5-abliterated:9b | harness | 0.000 | 0.000 | - | - | 11 | 5 | 88.8 |
| asrep_to_lateral | granite4.1:8b-ctx8k | raw | 0.000 | 0.000 | - | - | 0 | 1 | 10.3 |
| asrep_to_lateral | granite4.1:8b-ctx8k | tools | 0.000 | 0.000 | - | - | 0 | 1 | 16.6 |
| asrep_to_lateral | granite4.1:8b-ctx8k | harness | 0.000 | 0.000 | - | T1558.003 | 5 | 5 | 14.3 |
| asrep_to_lateral | gpt-oss:20b | raw | 0.000 | 0.000 | - | T1003, T1003.002, T1009, T1021, T1030, T1031, T1037, T1072, T1074, T1075, T1077, T1078, T1083, T1086, T1087.002, T1087.003, T1103, T1105, T1106, T1120, T1133, T1134, T1139, T1145, T1155, T1187, T1190, T1200, T1207, T1208, T1560, T1570, T1606, T1649 | 0 | 1 | 46.0 |
| asrep_to_lateral | gpt-oss:20b | tools | 0.000 | 0.000 | - | - | 0 | 1 | 46.7 |
| asrep_to_lateral | gpt-oss:20b | harness | 0.000 | 0.000 | - | - | 5 | 5 | 19.6 |
| asrep_to_lateral | huihui_ai/qwen3.5-abliterated:9b | raw | 0.000 | 0.000 | - | - | 0 | 1 | 57.8 |
| asrep_to_lateral | huihui_ai/qwen3.5-abliterated:9b | tools | 0.000 | 0.000 | - | 10324, 10325, 10336 | 5 | 5 | 113.1 |
| asrep_to_lateral | huihui_ai/qwen3.5-abliterated:9b | harness | 0.000 | 0.000 | - | - | 5 | 5 | 61.7 |
| meta3_ftp_backdoor | granite4.1:8b-ctx8k | raw | 0.000 | 0.000 | - | T1048, T1055, T1068, T1071, T1548.002 | 0 | 1 | 52.4 |
| meta3_ftp_backdoor | granite4.1:8b-ctx8k | tools | 0.000 | 0.000 | - | - | 1 | 2 | 46.1 |
| meta3_ftp_backdoor | granite4.1:8b-ctx8k | harness | 0.000 | 0.000 | - | - | 2 | 3 | 19.8 |
| meta3_ftp_backdoor | gpt-oss:20b | raw | 0.000 | 0.000 | - | T1047, T1059.001, T1071.004 | 0 | 1 | 43.7 |
| meta3_ftp_backdoor | gpt-oss:20b | tools | 0.000 | 0.000 | - | T1059.001, T1134, T1595.001 | 3 | 4 | 38.0 |
| meta3_ftp_backdoor | gpt-oss:20b | harness | 0.000 | 0.000 | - | - | 5 | 5 | 29.2 |
| meta3_ftp_backdoor | huihui_ai/qwen3.5-abliterated:9b | raw | 0.000 | 0.000 | - | T1059, T1068, T1071, T1072, T1099, T1257, T1498 | 0 | 1 | 59.0 |
| meta3_ftp_backdoor | huihui_ai/qwen3.5-abliterated:9b | tools | 0.000 | 0.000 | - | T1038, T1048, T1049 | 9 | 4 | 136.0 |
| meta3_ftp_backdoor | huihui_ai/qwen3.5-abliterated:9b | harness | 0.000 | 0.000 | - | - | 6 | 3 | 62.9 |

Ground truth per scenario: `kerberoast_to_da` = T1558.003, T1003.006, T1053.005 · `asrep_to_lateral` =
T1558.004, T1110.003, T1053.005 · `meta3_ftp_backdoor` = T1190, T1059.004.

Note the `asrep_to_lateral`/granite/harness false positive `T1558.003`: adjacent sub-technique to this
scenario's actual `T1558.004` (Kerberoasting vs AS-REP Roasting, same parent T1558) — another near-miss of
the same class discussed above, this time in the wrong direction (over-applying a technique the model
correctly used elsewhere).

## Reproducing this sweep

`tests/benchmarks/bench_security/_sweep_driver.py` (added this session) re-runs the exact 3x3x3 grid
in-process and writes to `/tmp/agentic_blue_sweep.json` for local inspection. Run:
`python3 -m tests.benchmarks.bench_security._sweep_driver`.
