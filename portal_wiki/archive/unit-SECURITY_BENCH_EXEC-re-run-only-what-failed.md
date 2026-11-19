---
id: unit-SECURITY_BENCH_EXEC-re-run-only-what-failed
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Re-run only what failed"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Re-run only what failed
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

python3 -m tests.benchmarks.bench_security --retry-failed results/sec_bench_20260624.json --chain-models ...
