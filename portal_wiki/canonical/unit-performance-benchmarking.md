---
id: unit-performance-benchmarking
kind: what
title: "PERFORMANCE \u2014 Benchmarking"
sources:
- type: doc
  path: docs/PERFORMANCE.md
  commit: 05e42ec2
  section: Benchmarking
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.510845
updated_at: 1784946220.510845
---

Run TPS benchmarks with:
```bash
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace auto --runs 3
```

Compare direct vs pipeline paths to identify overhead.
