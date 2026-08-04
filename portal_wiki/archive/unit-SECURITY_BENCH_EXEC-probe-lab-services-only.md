---
id: unit-SECURITY_BENCH_EXEC-probe-lab-services-only
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Probe lab services only"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Probe lab services only
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.901341
updated_at: 1783195000.901341
---


```bash
python3 -m tests.benchmarks.bench_security --probe-lab --dry-run 2>&1
```

---
