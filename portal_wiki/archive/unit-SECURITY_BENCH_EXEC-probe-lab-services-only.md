---
id: unit-SECURITY_BENCH_EXEC-probe-lab-services-only
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Probe lab services only"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Probe lab services only
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---


```bash
python3 -m tests.benchmarks.bench_security --probe-lab --dry-run 2>&1
```

---
