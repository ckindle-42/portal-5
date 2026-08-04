---
id: unit-tests-common
kind: mixed
title: "Tests common \u2014 shared refusal-phrase vocabulary"
sources:
- type: code
  path: tests/common.py
  commit: 4900007a
last_generated_commit: 4900007a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785798774.4436202
updated_at: 1785798774.4436202
---

`tests/common.py` holds the shared constants used by the acceptance driver,
the UAT driver, and the bench — most importantly `REFUSAL_PHRASES`, the
single maintained list of phrases that indicate a model refused a request.

## Why

Refusal detection is used as a `not_contains` keyword check in many tests,
and every new refusal variant a model produces (or a new phrasing style)
needed updating every test that checked for it. Maintaining the list in one
place means adding a new refusal variant updates every test simultaneously —
the difference between a one-line change and a hunt through a dozen files
for the same literal.

## Interfaces

`REFUSAL_PHRASES` and the other shared constants the drivers and benches
import.

## Gotchas

The list is deliberately coarse (matching common refusal phrasings) — a
model that refuses in an unusual phrasing may evade the keyword check, which
is an accepted limitation of keyword-based detection.
