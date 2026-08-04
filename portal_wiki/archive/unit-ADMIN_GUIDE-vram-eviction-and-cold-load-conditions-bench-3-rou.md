---
id: unit-ADMIN_GUIDE-vram-eviction-and-cold-load-conditions-bench-3-rou
kind: why
title: "ADMIN_GUIDE \u2014 VRAM eviction and cold-load conditions bench (3 router\
  \ candidates \xD7 4 scenarios)"
sources:
- type: design
  path: docs/ADMIN_GUIDE.md
  section: "VRAM eviction and cold-load conditions bench (3 router candidates \xD7\
    \ 4 scenarios)"
last_generated_commit: ''
confidence: high
tags:
- docs
- ADMIN_GUIDE
created_at: 1783195000.818524
updated_at: 1783195000.818524
---

OLLAMA_URL=http://localhost:11434 python3 tests/benchmarks/bench_router_conditions.py \
  --companions devstral:24b granite4.1:8b
```

Results are written to `tests/benchmarks/results/`.
