---
id: unit-performance-p7-perf-pipeline-optimizations
kind: what
title: "PERFORMANCE \u2014 P7-PERF Pipeline Optimizations"
sources:
- type: code
  path: portal/platform/inference/cluster_backends.py
- type: code
  path: portal/platform/inference/router/routing.py
- type: code
  path: tests/benchmarks/bench/measure.py
last_generated_commit: 9ec2fd4984c047ba49d9056db6a9666a1a4f0caf
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.508598
updated_at: 1784946220.508598
---

`P7-PERF` is the comment marker for a batch of pipeline routing optimizations measured against `bench_tps.py` output. Grepping for `P7-PERF` surfaces the affected paths rather than any single module:

- `cluster_backends.py` — the TTL-cached backend candidate list (`get_backend_candidates`), cache invalidation on health changes, and the cache-first fast path with unknown-id clamping.
- `router/routing.py` — reuse of the shared `httpx` client by the LLM router and the pre-compiled `_KEYWORD_CACHE` in the keyword scorer.
- `tests/benchmarks/bench/measure.py` — the module-level reusable bench `httpx.Client` (`_get_bench_client`).

The common theme is turning per-request work into import-time or first-use work: candidate lists, keyword dicts, and HTTP connection pools are each built once and reused across the steady-state request path.

## Why

The marker exists because these optimizations were driven by benchmark evidence rather than speculation: `bench_tps.py` highlighted routing overhead that sat between the raw Ollama endpoint and the pipeline endpoint, and each `P7-PERF` comment anchors a specific fix back to that measurement. Keeping the marker in the code makes the relationship between each optimization and its measured motivation auditable at the exact line where the shortcut lives, which matters because routing shortcuts are exactly the kind of change later readers hesitate to touch without knowing why it is there.
