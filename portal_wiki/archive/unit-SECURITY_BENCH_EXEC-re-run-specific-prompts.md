---
id: unit-SECURITY_BENCH_EXEC-re-run-specific-prompts
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Re-run specific prompts"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Re-run specific prompts
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

python3 -m tests.benchmarks.bench_security --retry-prompts kerberoasting pass_the_hash --chain-models ...
```
