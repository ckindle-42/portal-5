---
id: unit-tests-acceptance-v6-shim
kind: mixed
title: "Tests acceptance v6 \u2014 entry + section structure shim"
sources:
- type: code
  path: tests/portal5_acceptance_v6.py
  commit: 4900007a
last_generated_commit: 4900007a
claims: []
confidence: high
tags:
- authored-v1
- tests
created_at: 1785798808.12076
updated_at: 1785798808.12076
---

`portal5_acceptance_v6.py` is the stable entry point for the V6 acceptance
driver; the implementation lives in `tests/acceptance/`, and this file
delegates so existing invocations and the section-table regenerator keep
working.

## Why

The acceptance suite was split into a package, and the section-table
regenerator introspects this file's section structure — so the entry must
keep its shape. The shim preserves the invocation (`--section S3`,
`--skip-passing`) and the section definitions that downstream tooling
depends on.

## Interfaces

Delegates to the acceptance package's CLI with the section filtering
options.

## Gotchas

Because the regenerator introspects the section functions, a change to the
section structure here must be reflected in the section-table generator.
