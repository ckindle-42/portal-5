---
id: unit-SECURITY_BENCH_EXEC-3-stealth-scoring-appears
kind: why
title: "SECURITY_BENCH_EXEC \u2014 3. Stealth scoring appears"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 3. Stealth scoring appears
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.9103649
updated_at: 1783195000.9103649
---


```bash
grep "STEALTH" /tmp/secbench_full.log
```

Expected: `[STEALTH] kerberoast: 3 events ({4769: 3})` for each step that defines `stealth_event_ids`.
