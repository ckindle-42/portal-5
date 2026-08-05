---
id: unit-portal5-bench-execute-v4-results-dashboard
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Results + dashboard"
sources:
- type: code
  path: scripts/update_grafana_benchmarks.py
- type: code
  path: tests/benchmarks/bench/config.py
last_generated_commit: 3ddc2edf72414664d711390cd563cfb3e02f9130
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.7031198
updated_at: 1784946220.7031198
---

1. Confirm the run completed the planned test count (allow documented skips).
2. Update `config/grafana/dashboards/portal5_benchmarks.json` from the results
   JSON via the updater:
   ```bash
   python3 scripts/update_grafana_benchmarks.py --input tests/benchmarks/results/<file>.json
   ```
3. Commit:
   ```bash
   git add tests/benchmarks/results/<file>.json config/grafana/dashboards/portal5_benchmarks.json
   git commit -m "bench(tps): run <date> — <N> tests, <notable findings>"
   ```

## Why

`scripts/update_grafana_benchmarks.py` reads a bench_tps results JSON and
rewrites `config/grafana/dashboards/portal5_benchmarks.json` (its
`DASHBOARD_PATH` constant), rendering the direct/pipeline/persona tables from
the JSON's `avg_tps` fields. The updater and the results file must be committed
together so the dashboard and its source stay in sync; results live under
`tests/benchmarks/results/` per `RESULTS_DIR` in
`tests/benchmarks/bench/config.py`. Confirming the count first prevents a
partial run from being blessed as a baseline.
