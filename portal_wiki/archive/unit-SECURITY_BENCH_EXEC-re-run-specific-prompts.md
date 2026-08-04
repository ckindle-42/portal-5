---
id: unit-SECURITY_BENCH_EXEC-re-run-specific-prompts
kind: why
title: "SECURITY_BENCH_EXEC \u2014 Re-run specific prompts"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: Re-run specific prompts
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.906473
updated_at: 1783195000.906473
---

python3 -m tests.benchmarks.bench_security --retry-prompts kerberoasting pass_the_hash --chain-models ...
```
