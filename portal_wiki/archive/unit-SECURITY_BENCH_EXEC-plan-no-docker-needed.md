---
id: unit-SECURITY_BENCH_EXEC-plan-no-docker-needed
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Plan (no Docker needed):"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 'Plan (no Docker needed):'
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

python3 -m tests.benchmarks.bench_security --matrix-all --dry-run
