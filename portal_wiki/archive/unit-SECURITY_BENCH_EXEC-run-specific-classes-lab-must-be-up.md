---
id: unit-SECURITY_BENCH_EXEC-run-specific-classes-lab-must-be-up
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Run specific classes (lab must be up):"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 'Run specific classes (lab must be up):'
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

python3 -m tests.benchmarks.bench_security \
    --matrix-classes deserialization,sqli-auth-bypass,lfi-path-traversal \
    --lab-exec --max-concurrent 2
