---
id: unit-portal5-bench-execute-v4-served-model-sanity-new-in-v4
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Served-model sanity (new in V4)"
sources:
- type: code
  path: tests/benchmarks/bench/measure.py
- type: code
  path: tests/expected_models.py
- type: code
  path: scripts/persona_intent_audit.py
- type: code
  path: scripts/routing_regression.py
last_generated_commit: 1c013743834d850604632980a093809f65c3c3ed
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.70277
updated_at: 1784946220.70277
---

Persona served-model correctness was a recent bug class, so V4 adds a sanity
check. The bench records the model the API actually returned as `routed_model`
and a boolean `expected_model_match` per test (`tests/benchmarks/bench/measure.py`);
the expected keys come from `tests/expected_models.py`
(`expected_model_keys`, `model_matches_expected`). Grep the results JSON for
persona-mode entries and confirm `expected_model_match` is not false where the
requested workspace's model_hint should have been served.

Because `model_pin` is applied by the pipeline only when the request model is a
persona slug (not in bench persona mode), pin-serving correctness is verified
by `scripts/persona_intent_audit.py` (Check 2/3/5) and by
`scripts/routing_regression.py --assert-baseline`.

## Why

Served-model bugs were invisible to TPS alone: a persona can bench fine while
the pipeline silently serves its workspace's pool default instead of the
intended model. The bench therefore records `routed_model` and
`expected_model_match` so a mismatch is visible in the JSON, and the intent
audit plus the routing-regression baseline assert the full
`(base, variant, served_model)` tuple against a versioned corpus — the two
checks cover the paths the bench's own request shape cannot reach.
