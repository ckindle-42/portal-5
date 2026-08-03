---
id: unit-tests-lib-compliance-assertions
kind: mixed
title: "Tests lib compliance assertions \u2014 durable-methodology checks"
sources:
- type: code
  path: tests/lib/compliance_assertions.py
  commit: f2f2516d
last_generated_commit: f2f2516d
claims: []
confidence: high
tags:
- authored-v1
- tests
- lib
created_at: 1785798271.8809888
updated_at: 1785798271.8809888
---

`compliance_assertions.py` holds the behavioral assertions for
compliance-persona responses, each a pure function returning an
`AssertionResult` that the harness combines into a per-(persona, model,
scenario) outcome.

## Why

The assertion philosophy (from the compliance reframe) is to test durable
methodology, not volatile values: assertions reference the structural
patterns the personas mandate — output columns, classification tokens,
refusal phrases — rather than specific requirement numbers, enforcement
dates, or framework-of-the-month details. That distinction is what keeps the
compliance matrix meaningful as regulations change: the persona's mandated
method (classify, cite, refuse when unsupported) is stable even when the
specific requirements it references are not.

## Interfaces

The pure assertion functions, the `AssertionResult` type with its
MUST/SHOULD/INFO severities, and the combination logic the harness uses to
build a scenario outcome.

## Gotchas

A compliance persona that names a now-outdated requirement would still pass
its structural assertions — which is the point: the tests certify method, not
the currency of any specific rule.
