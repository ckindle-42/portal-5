---
id: unit-SECURITY_BENCH_EXEC-1-adaptive-retry-with-fallback-techniques
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 1. Adaptive Retry with Fallback Techniques"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 1. Adaptive Retry with Fallback Techniques
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

Each step can define `fallback_techniques` — alternative commands tried when the primary approach fails (`[EXEC ERR]`). On round 2+, missed steps get alternative commands injected into the retry directive.
