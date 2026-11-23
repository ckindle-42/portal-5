---
id: unit-tests-frontends-namespace
kind: mixed
title: "Tests frontends \u2014 OWUI-only test helper namespace"
sources:
- type: code
  path: tests/frontends/__init__.py
  commit: 38123c31
claims:
- probe: repo.path.exists
  path: tests/frontends/__init__.py
  equals: true
confidence: high
tags:
- authored-v1
- tests
- frontends
---

The frontends test package is a namespace marker for frontend-specific test
helpers. It exists to record the platform decision that Open WebUI is the
sole supported GUI frontend. The legacy UAT driver helpers (`tests/uat`)
were retired; OWUI-driven test coverage now lives in the self-contained
`tests/qat` suite.

## Why

Declaring the frontend boundary explicitly in a package docstring prevents a
future task from adding a second GUI frontend's driver helpers here while
Open WebUI remains the only supported one — the helpers would have no home
convention and would fragment the test tooling. The namespace records that any
frontend-specific helper belongs with the OWUI-driven suite, not in a new
package that would split the tooling by GUI.

## Interfaces

No callable surface — the `__init__.py` is a documentation marker.
