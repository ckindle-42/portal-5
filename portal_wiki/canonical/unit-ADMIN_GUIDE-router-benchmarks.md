---
id: unit-ADMIN_GUIDE-router-benchmarks
kind: why
title: "ADMIN_GUIDE \u2014 Router Benchmarks"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: Router Benchmarks
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.818032
updated_at: 1783195000.818032
---


To re-validate router accuracy after model changes:
```bash
OLLAMA_URL=http://localhost:11434 python3 tests/benchmarks/bench_router.py
OLLAMA_URL=http://localhost:11434 python3 tests/benchmarks/bench_router_conditions.py \
  --companions devstral:24b granite4.1:8b
```

Results are written to `tests/benchmarks/results/`.
