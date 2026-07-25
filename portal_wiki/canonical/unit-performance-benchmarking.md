---
id: unit-PERFORMANCE-benchmarking
kind: why
title: "PERFORMANCE \u2014 Benchmarking"
sources:
- type: design
  path: docs/PERFORMANCE.md
  section: Benchmarking
last_generated_commit: ''
confidence: high
tags:
- docs
- PERFORMANCE
created_at: 1783195000.881315
updated_at: 1783195000.881315
---


Run TPS benchmarks with:
```bash
python3 tests/benchmarks/bench_tps.py --mode pipeline --workspace auto --runs 3
```

Compare direct vs pipeline paths to identify overhead.
