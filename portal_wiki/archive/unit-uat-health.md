---
id: unit-uat-health
kind: mixed
title: "UAT health \u2014 backend/memory/zombie checks"
sources:
- type: code
  path: tests/uat/health.py
  commit: d7dcc96a
claims:
- probe: repo.path.exists
  path: tests/uat/health.py
  equals: true
confidence: high
tags:
- authored-v1
- tests
- uat
historical: true
---

Backend health, memory pressure, and OOM/zombie detection for the UAT driver.

## Why

A UAT run needs healthy backends before it starts, and it needs to notice when memory pressure or a zombie process threatens the run mid-way. The health module centralises those checks so every section that assumes a healthy stack starts from the same verification. The co-location note (`_backend_alive` lives here) exists so unit tests can monkeypatch the exact function the driver calls.

## Interfaces

`_backend_alive`, `_wait_for_backend_alive`, and the memory/OOM/zombie checks.

## Gotchas

The monkeypatch targets are co-located here deliberately — patch `tests.uat.health._backend_alive`, not a re-export.
