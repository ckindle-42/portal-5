---
id: unit-compliance-fallback-policy-granite-4-1-initial-expectation
kind: what
title: "COMPLIANCE_FALLBACK_POLICY \u2014 Granite 4.1 \u2014 initial expectation"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
- type: code
  path: tests/fixtures/compliance_scenarios.yaml
- type: code
  path: tests/lib/compliance_assertions.py
last_generated_commit: 1ed83b22525c97ed996c835b7519e10c75d13ad0
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.56481
updated_at: 1784946220.56481
---

Granite 4.1's model-card claims are recorded in the `bench-granite41-8b` and `bench-granite41-30b` workspace descriptions in `config/portal.yaml`. The 8B is described as a dense no-think model at roughly 5.3GB Q4_K_M, Apache 2.0 licensed and ISO-certified, with BFCL V3 68.3, IFEval 87.1 and GSM8K 92.5; the 30B as dense no-think at roughly 17GB Q4_K_M, Apache 2.0 and ISO-certified with cryptographic signatures, BFCL V3 73.7 (first on the IBM chart), IFEval 89.7, GSM8K 94.2 and EvalPlus 82.7, trained with GRC data curation for compliance and audit workflows.

The expectations the sweep will test are encoded in `tests/fixtures/compliance_scenarios.yaml`: the `dense-structured-tool-output` scenario description states dense no-think models should pass it cleanly while reasoning models typically warn on emitted think blocks, and the classification, citation-format, anti-fabrication and insufficient-context scenarios carry assertion specs dispatched by `run_assertions` to `tests/lib/compliance_assertions.py`. If the first run disappoints, the operator's knobs are the persona system prompt (`config/personas/*.yaml`), the assertion regexes in `tests/lib/compliance_assertions.py`, and model group membership in `config/backends.yaml`.

## Why

The source document's expectation prose is a prediction, so the only verifiable half is the model-card data recorded in the bench workspace descriptions and the fixture comments stating the intended outcome. Rewording the failure guidance to name the three configuration surfaces the operator can actually touch turns a speculative paragraph into a grounded decision checklist.
