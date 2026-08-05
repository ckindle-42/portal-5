---
id: unit-portal5-bench-sec-execute-v3-candidate-qualification-report
kind: what
title: "PORTAL5_BENCH_SEC_EXECUTE_V3 \u2014 Candidate qualification report"
sources:
- type: code
  path: portal/modules/security/core/commands/run.py
- type: code
  path: portal/modules/security/core/scoring.py
- type: code
  path: portal/modules/security/core/candidate_eval.py
- type: code
  path: portal/modules/security/core/exec_chain.py
last_generated_commit: 794b3575d040c73f2c2af8ad7a8bca350ad57e4b
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.709623
updated_at: 1784946220.709623
---

The qualification report summarizes the scored rows `run_bench` returns. Per
variant, the theory pass yields `score_response` metrics — `header_score`
(structured-output adherence to the prompt's `required_headers`), MITRE
coverage, and disclaimer penalties — and the execution pass yields
`score_execution` metrics: `step_coverage` and `proven_coverage` (chain
completion), `sequence_adherence` (tool-call ordering via longest increasing
subsequence), and `tool_diversity`. Chain runs add `chain_models_with_calls`
versus `chain_total_models` (engagement), handoff quality, and, under live
execution, `lab_success` plus blue `steps_detected` when telemetry is up. For
execution workspaces the report records whether the live-lab steps actually
executed and were detected. Promotion follows `PROMOTE_POLICY=confirm` (see
`candidate_eval.py`): the report recommends operator action and records a gate
clearance but never swaps fleet config automatically. Finally, the operator
commits the output JSON — default `results/sec_bench_<timestamp>.json` — and
any scoreboard update.

## Why

The report is the deliverable that turns raw JSON into a promotion decision,
and its rules exist to keep that decision conservative. Zero auto-promotion is
the load-bearing guarantee: a passing candidate is a recommendation and a
clearance record, so a bench artifact can never silently change which model the
fleet serves.
