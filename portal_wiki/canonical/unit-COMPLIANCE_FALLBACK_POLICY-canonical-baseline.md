---
id: unit-COMPLIANCE_FALLBACK_POLICY-canonical-baseline
kind: why
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Canonical baseline"
sources:
- type: design
  path: docs/COMPLIANCE_FALLBACK_POLICY.md
  section: Canonical baseline
last_generated_commit: ''
confidence: high
tags:
- docs
- COMPLIANCE_FALLBACK_POLICY
created_at: 1783195000.833091
updated_at: 1783195000.833091
---


Operator stores the accepted baseline at:
```
tests/benchmarks/results/persona_matrix_baseline.json
```

Re-baselining cadence: quarterly, or after any of the following changes:

- New model added to `ollama-reasoning` / `ollama-general`
- Existing model upgraded (Ollama re-pull moves the digest)
- Persona system prompt edited (TASK_COMPLIANCE_REFRAME class changes)
- Fixture scenario added or modified
- Assertion library threshold or regex changed
