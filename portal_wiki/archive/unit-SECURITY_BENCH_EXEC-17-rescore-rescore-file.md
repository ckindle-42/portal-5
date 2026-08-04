---
id: unit-SECURITY_BENCH_EXEC-17-rescore-rescore-file
kind: why
title: "SECURITY_BENCH_EXEC \u2014 17. Rescore (`--rescore FILE`)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 17. Rescore (`--rescore FILE`)
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.905569
updated_at: 1783195000.905569
---

Reads a previous result JSON and re-derives scoring metrics from saved tool calls and lab observations without re-executing. Useful for tuning scoring parameters or validating results after code changes.

```bash
python3 -m tests.benchmarks.bench_security --rescore results/sec_bench_20260624.json
```
