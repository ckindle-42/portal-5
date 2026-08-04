---
id: unit-V2_SCENARIO_AUDIT_V1-scenarios-from-uat-pass-predecessors-6-of-15
kind: why
title: "V2_SCENARIO_AUDIT_V1 \u2014 Scenarios from UAT-PASS predecessors (6 of 15)"
sources:
- type: design
  path: docs/V2_SCENARIO_AUDIT_V1.md
  section: Scenarios from UAT-PASS predecessors (6 of 15)
last_generated_commit: ''
confidence: high
tags:
- docs
- V2_SCENARIO_AUDIT_V1
created_at: 1783195000.9270332
updated_at: 1783195000.9270332
---


These regression guards serve as stability checks. All 6 passed for Laguna under V2, confirming no regression. No unexpected behavior observed. Two notes:

- `creative-particle-system`: V2 simplifies the interaction model (space-bar emission vs click-position emission, drops gravity toggle and clear-key), but since both pass this doesn't represent a bias concern.
- `k8s-manifest-complete`: V2 broadens scope (adds Service manifest, rolling update, rollback comment) and mandates a fenced code block — an output-format prescription that UAT didn't have. Since UAT passed without format prescription, this is a task-scope change rather than a rescued failure.
