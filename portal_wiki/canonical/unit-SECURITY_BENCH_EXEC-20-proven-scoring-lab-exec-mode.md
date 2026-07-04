---
id: unit-SECURITY_BENCH_EXEC-20-proven-scoring-lab-exec-mode
kind: why
title: "SECURITY_BENCH_EXEC \u2014 20. Proven Scoring (Lab-Exec Mode)"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 20. Proven Scoring (Lab-Exec Mode)
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.906991
updated_at: 1783195000.906991
---

In lab-exec mode, the composite score uses `proven_coverage` (steps confirmed successful) instead of `step_coverage` (steps attempted). A failed exploit no longer scores the same as a successful one.

| Mode | Coverage metric | Meaning |
|------|----------------|---------|
| Synthetic (no lab) | `step_coverage` | All hits count as proven |
| Lab-exec | `proven_coverage` | Only hits with success_indicators in output |

Fields: `steps_proven`, `steps_attempted`, `success_rate`, `has_lab_output`, `proven_coverage`.
