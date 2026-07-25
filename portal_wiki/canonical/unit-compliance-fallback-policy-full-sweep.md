---
id: unit-compliance-fallback-policy-full-sweep
kind: what
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Full sweep"
sources:
- type: doc
  path: docs/COMPLIANCE_FALLBACK_POLICY.md
  commit: 05e42ec2
  section: Full sweep
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5655859
updated_at: 1784946220.5655859
---

python3 tests/portal5_persona_matrix.py \
    --output tests/benchmarks/results/persona_matrix_$(date -u +%Y%m%dT%H%M%SZ).json
