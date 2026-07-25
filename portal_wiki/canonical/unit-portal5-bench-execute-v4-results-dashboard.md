---
id: unit-portal5-bench-execute-v4-results-dashboard
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Results + dashboard"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_EXECUTE_V4.md
  commit: 05e42ec2
  section: Results + dashboard
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.7031198
updated_at: 1784946220.7031198
---

1. Confirm the run completed the planned test count (allow documented skips).
2. Update `config/grafana/dashboards/portal5_benchmarks.json` from the results
   JSON via the existing updater (confirm its name):
   ```bash
   python3 scripts/update_grafana_benchmarks.py --input tests/benchmarks/results/<file>.json
   ```
3. Commit:
   ```bash
   git add tests/benchmarks/results/<file>.json config/grafana/dashboards/portal5_benchmarks.json
   git commit -m "bench(tps): run <date> — <N> tests, <notable findings>"
   ```

---
