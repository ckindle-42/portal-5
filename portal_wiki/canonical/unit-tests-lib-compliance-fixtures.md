---
id: unit-tests-lib-compliance-fixtures
kind: mixed
title: "Tests lib compliance fixtures \u2014 YAML scenario parameterizer"
sources:
- type: code
  path: tests/lib/compliance_fixtures.py
  commit: f2f2516d
last_generated_commit: f2f2516d
claims: []
confidence: high
tags:
- authored-v1
- tests
- lib
created_at: 1785798277.837648
updated_at: 1785798277.837648
---

`compliance_fixtures.py` loads and parameterizes
`tests/fixtures/compliance_scenarios.yaml` into concrete
(persona_slug, framework, prompt, assertion_callables) tuples that the
acceptance and matrix harnesses iterate. The fixture YAML is the single
source of truth; the Python is purely a transform.

## Why

A compliance scenario is a pairing of a persona, a framework, a prompt, and
the assertions that define a passing response, and that pairing belongs in
the fixture file where a human edits it, not in code where a harness would
need a rebuild to change it. The loader makes the YAML executable: it
resolves the assertion names into callables so the harness iterates concrete
tuples instead of re-parsing YAML per scenario.

## Interfaces

The loader and parameterizer produce the concrete scenario tuples consumed
by the acceptance and matrix harnesses.

## Gotchas

An assertion name in the YAML that has no corresponding function in the
assertion module is a silent no-op — the loader should fail loudly on an
unknown assertion reference.
