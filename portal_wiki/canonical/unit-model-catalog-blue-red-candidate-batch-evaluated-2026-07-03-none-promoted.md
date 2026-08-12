---
id: unit-model-catalog-blue-red-candidate-batch-evaluated-2026-07-03-none-promoted
kind: what
title: "MODEL_CATALOG \u2014 Blue/red candidate batch evaluated 2026-07-03 \u2014\
  \ none promoted"
sources:
- type: code
  path: portal/modules/security/core/candidate_eval.py
- type: code
  path: tests/benchmarks/results/v10_candidates_20260629T194541Z.json
last_generated_commit: 206d6a3f87fd93be416be23d7878a5f6c23e7cb5
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.623596
updated_at: 1784946220.623596
---

The candidate-evaluation harness `portal/modules/security/core/candidate_eval.py` benches
one new model against a slot incumbent, computes per-scenario and aggregate deltas, and
writes an isolated per-candidate result file `cand_*.json` under
`portal/modules/security/core/results/candidates/`. Files actually present there include
`cand_ravenx-cyberagent-35b_Q4_K_M_exploit_20260703T141854Z.json`,
`cand_hf.co_RedTeamLab_Qwen3.6-27B-redteam-v5_qwen3.6-27b-redteam-v5-Q4_K_M.gguf_exploit_20260703T154522Z.json`,
and `cand_huihui_ai_baronllm-abliterated_latest_exploit_20260704T055814Z.json`, alongside
`blue_*` runs from the same candidate pool — the 2026-07-03 batch compared blue and red
candidates. Because `PROMOTE_POLICY=confirm`, the harness reports deltas and never swaps
fleet config, so a candidate batch always ends as comparison records with nothing
promoted. The `TASK_MODEL_EVAL_V10_CANDIDATES` probe run in
`tests/benchmarks/results/v10_candidates_20260629T194541Z.json` records per-workspace
probe scores for the bench-* candidate workspaces.

## Why

This unit previously pointed at raw result paths under a `bench_security` results
directory that does not exist and asserted unverifiable detail about a full-coverage
run and its scoring. The harness and its isolated cand_* output path are the real
record: candidate_eval.py fixes where results live, PROMOTE_POLICY=confirm fixes why
nothing was promoted, and the V10 probe file supplies the scoring basis for the bench-*
workspaces. Unverifiable claims were deleted rather than softened so the summary stays
a faithful pointer to the data it describes.
