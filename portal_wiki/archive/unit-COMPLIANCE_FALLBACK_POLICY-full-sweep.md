---
id: unit-COMPLIANCE_FALLBACK_POLICY-full-sweep
historical: true
kind: why
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Full sweep"
sources:
- type: design
  path: docs/COMPLIANCE_FALLBACK_POLICY.md
  section: Full sweep
confidence: high
tags:
- docs
- COMPLIANCE_FALLBACK_POLICY

---

python3 tests/portal5_persona_matrix.py \
    --output tests/benchmarks/results/persona_matrix_$(date -u +%Y%m%dT%H%M%SZ).json
