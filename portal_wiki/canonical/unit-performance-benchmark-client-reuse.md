---
id: unit-PERFORMANCE-benchmark-client-reuse
kind: why
title: "PERFORMANCE \u2014 Benchmark Client Reuse"
sources:
- type: design
  path: docs/PERFORMANCE.md
  section: Benchmark Client Reuse
last_generated_commit: ''
confidence: high
tags:
- docs
- PERFORMANCE
created_at: 1783195000.881074
updated_at: 1783195000.881074
---

`bench_tps.py` reuses a single httpx client across all benchmark runs for accurate pipeline latency measurement.

---
