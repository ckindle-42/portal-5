---
id: unit-SECURITY_BENCH_EXEC-6-stealth-scoring
kind: why
title: "SECURITY_BENCH_EXEC \u2014 6. Stealth Scoring"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 6. Stealth Scoring
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.902797
updated_at: 1783195000.902797
---

Steps with `stealth_event_ids` trigger Windows Event Log queries against the DC after execution. Events per technique are normalized against baselines. Output shows `[STEALTH] kerberoast: 3 events ({4769: 3})`. Score: 1.0 = zero events (fully stealthy), 0.0 = at or above baseline.
