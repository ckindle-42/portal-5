---
id: unit-uat-results
kind: mixed
title: "UAT results \u2014 result model + emission"
sources:
- type: code
  path: tests/uat/results.py
  commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799315.5687082
updated_at: 1785799315.5687082
---

The UAT result model and emission, reading the result file attribute-form.

## Why

Every UAT section records a result, and the result model is the shared shape that makes a run's output comparable across sections and across runs. The attribute-form access note exists because the tests monkeypatch `tests.uat.config.RESULTS_FILE`, and results must see the rebind.

## Interfaces

The result model, recording, and emission functions.

## Gotchas

Results read `config.RESULTS_FILE` attribute-form so monkeypatching the config path takes effect.
