---
id: unit-SECURITY_BENCH_EXEC-blue-purple-on-web-classes
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Blue + purple on web classes:"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 'Blue + purple on web classes:'
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.9084811
updated_at: 1783195000.9084811
---

python3 -m tests.benchmarks.bench_security \
    --matrix-classes lfi-path-traversal --purple --dry-run
```

`--matrix-coverage` reports per-class/scenario: resolved containers, ran, verified by oracle, rejected. This is the "how much of the library are we testing" number.
