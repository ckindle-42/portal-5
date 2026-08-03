---
id: unit-tests-expected-models
kind: mixed
title: "Tests expected-models \u2014 config-derived routing ground truth"
sources:
- type: code
  path: tests/expected_models.py
  commit: 4900007a
last_generated_commit: 4900007a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785798786.555152
updated_at: 1785798786.555152
---

`expected_models.py` derives "what model should have served this request" from
the canonical config — the per-persona YAML and the backends — given a
workspace id or persona slug, without ever modifying them. The routing
checks in the acceptance driver use it to verify the served model matches
the expected one.

## Why

A routing test needs a ground truth for "correct": given a workspace or
persona, which model should the pipeline have served? Deriving it from the
same config that drives routing (rather than hardcoding a list) is what
keeps the expectation true as the fleet changes — a model reassignment in
config updates the expected answer automatically. The `model_matches_expected`
matching and the routing-identifier handling exist because the served model
may be reported as a workspace-level alias rather than the exact model id,
and the test must not fail on a legitimate alias.

## Interfaces

`expected_model_keys`, `expected_model_keys_for_persona`,
`model_matches_expected`, and `resolve_expected` are the surface the routing
checks call.

## Gotchas

The module reads the canonical config but never writes it — the expectation
is derived, not recorded, so a config edit cannot silently diverge from a
stale expected list.
