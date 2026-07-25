---
id: unit-compliance-fallback-policy-canonical-baseline
kind: what
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Canonical baseline"
sources:
- type: doc
  path: docs/COMPLIANCE_FALLBACK_POLICY.md
  commit: 05e42ec2
  section: Canonical baseline
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.564456
updated_at: 1784946220.564456
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
