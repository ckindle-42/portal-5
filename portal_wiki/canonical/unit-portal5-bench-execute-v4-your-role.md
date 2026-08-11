---
id: unit-portal5-bench-execute-v4-your-role
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Your Role"
sources:
- type: code
  path: tests/benchmarks/bench/config.py
- type: code
  path: scripts/update_grafana_benchmarks.py
last_generated_commit: 3771ef49a112fde1d667c67af5bf1bc003ce75b4
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.699299
updated_at: 1784946220.699299
---

You are the **benchmark execution agent**, not the implementation agent. You
execute the suite, diagnose failures, adjust the run, retry intelligently, and
produce a Grafana dashboard update. Results go to `tests/benchmarks/results/`
as a timestamped JSON (`RESULTS_DIR` / `RESULTS_FILE` in
`tests/benchmarks/bench/config.py`); the dashboard at
`config/grafana/dashboards/portal5_benchmarks.json` updates from that file via
`scripts/update_grafana_benchmarks.py`.

**No shortcuts. No prior-run bias.** Do not assume models from a previous run
are still loaded or producing similar TPS. Every run is fresh.

**Do NOT modify product code.** `portal/**` is protected. If a bench failure
traces to a product bug, report it — don't patch it here.

## Why

The role is deliberately separated from implementation so the bench stays a
measurement instrument: the execution agent adjusts run scope, diagnoses
failures, and reports product bugs without editing routing code, which keeps
results trustworthy. The read-only rule and fresh-run rule protect against the
two ways a bench corrupts itself — patching the code under test, or
over-trusting cached resident models — so the dashboard update reflects what
actually ran.
