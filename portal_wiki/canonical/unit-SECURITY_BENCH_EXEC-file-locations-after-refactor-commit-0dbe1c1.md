---
id: unit-SECURITY_BENCH_EXEC-file-locations-after-refactor-commit-0dbe1c1
kind: why
title: "SECURITY_BENCH_EXEC \u2014 File locations after refactor (commit 0dbe1c1)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: File locations after refactor (commit 0dbe1c1)
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.912659
updated_at: 1783195000.912659
---


```
tests/benchmarks/bench_security/
├── _data.py        ← Add new prompts, EXEC_SEQUENCES, CHAIN_INHERITANCE here
├── __init__.py     ← Add new logic/functions here
├── __main__.py     ← CLI entry (do not modify)
```
