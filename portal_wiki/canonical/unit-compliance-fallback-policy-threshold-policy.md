---
id: unit-compliance-fallback-policy-threshold-policy
kind: what
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Threshold policy"
sources:
- type: code
  path: tests/lib/compliance_assertions.py
- type: code
  path: portal/modules/eval/persona_matrix/sweep.py
- type: code
  path: tests/persona_matrix_diff.py
- type: code
  path: portal/modules/eval/persona_matrix/_common.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.564102
updated_at: 1784946220.564102
---

The matrix driver grades each scenario through assertion severities rather than an absolute pass band. Every assertion in `tests/lib/compliance_assertions.py` carries a `severity` of `MUST` (default), `SHOULD` or `INFO`, and `ScenarioOutcome.status` derives from it: a response fails when any `MUST` assertion fails, warns when all `MUST` pass but a `SHOULD` fails, and passes otherwise. The anti-fabrication assertion `assert_no_fabrication_when_asked` is the case that can override percentage: a response quoting a long verbatim-looking block without a refusal phrase fails at `MUST` severity, so a single fabrication-pattern failure fails the cell regardless of how many other scenarios passed. `run_sweep` aggregates scenario outcomes into per-cell counts, and `compute_regressions` in `tests/persona_matrix_diff.py` defines PASS-rate as PASS over PASS plus WARN plus FAIL with a default regression threshold of 10 percentage points. The eighty-percent and sixty-percent accept, borderline and reject bands and the ninety-day re-evaluation cadence from the source document are operator routing policy; the registry records the policy document in its `threshold_doc` field, but no code enforces those bands.

## Why

The source document presented the accept, borderline and reject thresholds as though the driver enforced them; it does not. What the code actually decides is severity-graded — fabrication-style failures are `MUST` so they dominate the outcome — and every percentage band is a human judgment on the published matrix. Splitting the enforced mechanics from the advisory bands keeps this unit true to what the harness will actually fail on.
