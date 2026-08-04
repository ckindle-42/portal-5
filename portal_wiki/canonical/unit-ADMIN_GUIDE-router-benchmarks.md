---
id: unit-ADMIN_GUIDE-router-benchmarks
kind: why
title: "ADMIN_GUIDE \u2014 Router Benchmarks"
sources:
- type: code
  path: tests/benchmarks/bench_router.py
- type: code
  path: tests/benchmarks/bench_router_conditions.py
- type: code
  path: .env.example
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- ADMIN_GUIDE
- docs
- verified-v1
created_at: 1783195000.818032
updated_at: 1783195000.818032
---

Router accuracy is re-measurable after any model or fleet change. `tests/benchmarks/bench_router.py` scores candidate models against the `GOLDEN_SET` of 73 test cases and writes a results JSON; `tests/benchmarks/bench_router_conditions.py` measures the companion-model cold-load conditions that affect warm latency. A typical invocation is:

```bash
OLLAMA_URL=http://localhost:11434 python3 tests/benchmarks/bench_router.py
```

Results land in `tests/benchmarks/results/`, and the published PRIMARY/STANDBY/FALLBACK accuracy figures in `.env.example` trace back to this bench.

## Why

Router quality is a measured property, not an assumption — the bench pins the accuracy numbers that justify the default model choice, so a swap can be validated against a fixed corpus before it is trusted in production routing. Keeping the corpus and the runner in the repo means the figures stay reproducible instead of remembered.
