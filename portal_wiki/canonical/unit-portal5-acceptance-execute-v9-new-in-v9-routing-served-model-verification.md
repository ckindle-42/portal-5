---
id: unit-portal5-acceptance-execute-v9-new-in-v9-routing-served-model-verification
kind: what
title: "PORTAL5_ACCEPTANCE_EXECUTE_V9 \u2014 New in V9 \u2014 routing + served-model\
  \ verification"
sources:
- type: code
  path: scripts/routing_regression.py
- type: code
  path: tests/acceptance/s10_personas_ollama.py
- type: code
  path: tests/expected_models.py
- type: code
  path: scripts/execute_preflight.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.695986
updated_at: 1784946220.695986
---

Routing integrity is verified in two layers. Before the suite, run
`scripts/routing_regression.py --assert-baseline`: it resolves the fixed corpus
in `tests/routing/corpus.json` through the keyword routing layer and asserts
the full `(base, variant, served_model)` tuple per prompt against
`tests/routing/baseline.json`, exiting non-zero on any drift. A failure means
routing has moved from its proven baseline — a product regression to report,
not to mask by adjusting acceptance expectations.

During S10, `s10_personas_ollama.py` passes each persona slug to
`_assert_routing`, which resolves the expected model through
`tests/expected_models.py` (`expected_model_keys_for_persona` via the runtime
`_PERSONA_MAP`) and compares it against the model the pipeline actually served.
`scripts/execute_preflight.py` enumerates the `model_pin` personas so the
operator knows which slugs must be served their pinned model. A persona that
resolves to the right workspace but is served the wrong model records a routing
mismatch and is flagged as a WARN — exactly the bug class the model-pin work
fixed, so a regression here is actionable.

## Why

Routing integrity was the source of a real production bug: a request could land
on the right workspace yet be served a model that is not the one its persona
pins, and id-only comparison would not catch it. The baseline gate and the S10
expected-model check therefore compare the served model, not just the
destination, so the suite fails loudly on the exact regression that previously
slipped through as a green routing result.
