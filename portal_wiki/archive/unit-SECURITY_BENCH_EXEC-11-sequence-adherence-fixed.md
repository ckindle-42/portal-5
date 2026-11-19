---
id: unit-SECURITY_BENCH_EXEC-11-sequence-adherence-fixed
historical: true
kind: why
title: "SECURITY_BENCH_EXEC \u2014 11. Sequence Adherence (Fixed)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 11. Sequence Adherence (Fixed)
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC

---

`sequence_adherence` now correctly measures execution order. Previously it recorded step indices (always sorted), making the metric meaningless. It now records the tool call index that matched each step, so out-of-order execution correctly penalizes adherence. Score: LIS of matched tool call indices / number of hits.
