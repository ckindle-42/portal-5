---
id: unit-PERSONA_MATRIX_CI-pipeline-shape
kind: why
title: "PERSONA_MATRIX_CI \u2014 Pipeline shape"
sources:
- type: design
  path: docs/PERSONA_MATRIX_CI.md
  section: Pipeline shape
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_MATRIX_CI
created_at: 1783195000.8818402
updated_at: 1783195000.8818402
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
