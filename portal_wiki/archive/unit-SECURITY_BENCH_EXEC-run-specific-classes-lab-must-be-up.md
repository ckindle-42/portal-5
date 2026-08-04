---
id: unit-SECURITY_BENCH_EXEC-run-specific-classes-lab-must-be-up
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Run specific classes (lab must be up):"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 'Run specific classes (lab must be up):'
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.908237
updated_at: 1783195000.908237
---

python3 -m tests.benchmarks.bench_security \
    --matrix-classes deserialization,sqli-auth-bypass,lfi-path-traversal \
    --lab-exec --max-concurrent 2
