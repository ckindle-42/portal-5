---
id: unit-SECURITY_BENCH_EXEC-re-run-only-what-failed
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Re-run only what failed"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Re-run only what failed
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.906101
updated_at: 1783195000.906101
---

python3 -m tests.benchmarks.bench_security --retry-failed results/sec_bench_20260624.json --chain-models ...
