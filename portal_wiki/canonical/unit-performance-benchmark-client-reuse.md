---
id: unit-performance-benchmark-client-reuse
kind: what
title: "PERFORMANCE \u2014 Benchmark Client Reuse"
sources:
- type: doc
  path: docs/PERFORMANCE.md
  commit: 05e42ec2
  section: Benchmark Client Reuse
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.510535
updated_at: 1784946220.510535
---

`bench_tps.py` reuses a single httpx client across all benchmark runs for accurate pipeline latency measurement.

---
