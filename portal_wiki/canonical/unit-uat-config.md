---
id: unit-uat-config
kind: mixed
title: "UAT config \u2014 env/constants/result paths"
sources:
- type: code
  path: tests/uat/config.py
  commit: 85bb65bd
last_generated_commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799258.369716
updated_at: 1785799258.369716
---

The env constants, timeouts, memory thresholds, and result paths for the UAT driver, extracted verbatim from the monolith.

## Why

Centralising the run's tuning values and paths in one module is what makes a UAT run reproducible — changing a timeout or the result file location is a one-line edit in config rather than a hunt through the driver. The monkeypatch-sensitivity note (always access `RESULTS_FILE` attribute-form) exists because the tests that monkeypatch it target the config module, and a value-copied import would not see the rebind.

## Interfaces

`RESULTS_FILE` and the other constants are read attribute-form so monkeypatching takes effect.

## Gotchas

The `from module import constant` form defeats monkeypatching — always access attribute-form.
