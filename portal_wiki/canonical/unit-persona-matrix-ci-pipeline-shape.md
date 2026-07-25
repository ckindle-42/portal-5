---
id: unit-persona-matrix-ci-pipeline-shape
kind: what
title: "PERSONA_MATRIX_CI \u2014 Pipeline shape"
sources:
- type: doc
  path: docs/PERSONA_MATRIX_CI.md
  commit: 05e42ec2
  section: Pipeline shape
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.567413
updated_at: 1784946220.567413
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
