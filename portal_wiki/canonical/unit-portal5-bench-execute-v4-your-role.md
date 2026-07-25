---
id: unit-portal5-bench-execute-v4-your-role
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Your Role"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_EXECUTE_V4.md
  commit: 05e42ec2
  section: Your Role
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.699299
updated_at: 1784946220.699299
---

You are the **benchmark execution agent**, not the implementation agent. You
execute the suite, diagnose failures, adjust the run, retry intelligently, and
produce a Grafana dashboard update. Results go to
`tests/benchmarks/results/` as a timestamped JSON; the dashboard at
`config/grafana/dashboards/portal5_benchmarks.json` updates from that file.

**No shortcuts. No prior-run bias.** Do not assume models from a previous run
are still loaded or producing similar TPS. Every run is fresh.

**Do NOT modify product code.** `portal/**` is protected. If a bench failure
traces to a product bug, report it — don't patch it here.

---
