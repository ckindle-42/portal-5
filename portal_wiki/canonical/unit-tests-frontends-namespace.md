---
id: unit-tests-frontends-namespace
kind: mixed
title: "Tests frontends \u2014 OWUI-only UAT helper namespace"
sources:
- type: code
  path: tests/frontends/__init__.py
  commit: '96146826'
claims: []
confidence: high
tags:
- authored-v1
- tests
- frontends
created_at: 1785795631.3447711
updated_at: 1785795631.3447711
---

The frontends test package is a namespace marker for frontend-specific UAT
driver helpers. It exists to record the platform decision that Open WebUI is
the sole supported GUI frontend — the UAT helpers themselves live in the
`tests/uat` package (`owui_api.py`, `browser.py`, `dispatch.py`), with
`tests/portal5_uat_driver.py` as the entry-point shim.

## Why

Declaring the frontend boundary explicitly in a package docstring prevents a
future task from adding a second GUI frontend's driver helpers here while
Open WebUI remains the only supported one — the helpers would have no home
convention and would fragment the UAT tooling. The namespace records that any
frontend-specific helper belongs in `tests/uat`, not in a new package that
would split the driver tooling by GUI.

## Interfaces

No callable surface — the `__init__.py` is a documentation marker. The UAT
helpers it points to live in the `tests/uat` package.
