---
id: unit-uat-init
kind: mixed
title: "UAT package \u2014 modularised UAT driver split"
sources:
- type: code
  path: tests/uat/__init__.py
  commit: 85bb65bd
last_generated_commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799254.7956119
updated_at: 1785799254.7956119
---

The uat package is the modularised UAT driver, split from the monolithic
`tests/portal5_uat_driver.py` into focused modules: config, state, freshness,
health, lifecycle, owui_api, routing, browser, dispatch, runner, grading,
results, and the rest. The operator entry point stays the top-level driver.

## Why

The driver monolith had grown past maintainability, and the modularisation
exists so each concern is a module with one job. The module map in the
docstring is the contract for where a new UAT feature belongs, and the
import-direction notes (lifecycle avoids importing health; owui_api
co-locates the monkeypatch targets) document the dependency rules that keep
the package testable.

## Interfaces

The package hosts the UAT modules; the top-level `portal5_uat_driver.py`
remains the operator-facing entry.

## Gotchas

Several modules document that they were extracted *verbatim* from the
monolith — the extraction preserved behaviour exactly, and new features
belong in the owning module, not back in the driver.
