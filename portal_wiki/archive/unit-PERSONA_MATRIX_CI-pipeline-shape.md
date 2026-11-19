---
id: unit-PERSONA_MATRIX_CI-pipeline-shape
historical: true
kind: why
title: "PERSONA_MATRIX_CI \u2014 Pipeline shape"
sources:
- type: design
  path: docs/PERSONA_MATRIX_CI.md
  section: Pipeline shape
confidence: high
tags:
- docs
- PERSONA_MATRIX_CI

---


```
[scheduled cron] ──┐
[PR-touching matrix code] ──┤── persona-matrix-nightly workflow
[manual dispatch] ──┘                │
                                     ▼
                          tests/portal5_persona_matrix.py sweep
                                     │
                                     ▼
                          tests/benchmarks/results/...json (artifact)
                                     │
                                     ▼
                          tests/persona_matrix_diff.py vs baseline
                                     │
                                     ▼
                          green or red CI status
```
