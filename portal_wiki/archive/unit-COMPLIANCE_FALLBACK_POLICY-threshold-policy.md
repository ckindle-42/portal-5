---
id: unit-COMPLIANCE_FALLBACK_POLICY-threshold-policy
kind: why
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Threshold policy"
sources:
- type: design
  path: docs/COMPLIANCE_FALLBACK_POLICY.md
  section: Threshold policy
last_generated_commit: ''
confidence: high
tags:
- docs
- COMPLIANCE_FALLBACK_POLICY
created_at: 1783195000.832871
updated_at: 1783195000.832871
---


The persona matrix driver
(`tests/portal5_persona_matrix.py`) produces a per-(persona, model) result
matrix using the assertion library in `tests/lib/compliance_assertions.py`
against scenarios in `tests/fixtures/compliance_scenarios.yaml`.

For each model, summed across all 7 compliance personas:

| Outcome | Per-cell rule | Routing action |
|---|---|---|
| **Acceptable fallback** | &ge;80% of MUST assertions PASS, no scenario shows fabricated verbatim text | Keep current routing position |
| **Borderline** | 60&ndash;80% MUST PASS, no fabrications | Move to back of group; flag for re-evaluation in 90 days |
| **Reject** | <60% MUST PASS, OR any fabrication-pattern failure | Remove from compliance routing groups; remains available via direct workspace targeting |

Special-case rule: **fabrication failures override percentage**. A model
that confabulates verbatim requirement text on any scenario is rejected
regardless of overall PASS rate. Fabrication is the highest-stakes
behavior in compliance work.
