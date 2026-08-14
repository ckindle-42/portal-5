---
id: unit-uat-owui_api
kind: mixed
title: "UAT OWUI API \u2014 REST helpers + chat archival"
sources:
- type: code
  path: tests/uat/owui_api.py
  commit: 85bb65bd
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785799286.397863
updated_at: 1785799286.397863
---

The Open WebUI REST helpers: login, chat creation, message send, response retrieval, and chat archival.

## Why

The UAT driver drives the real Open WebUI, and the API module is the single wrapper over OWUI's REST endpoints — the difference between the driver calling OWUI consistently and each section embedding its own HTTP calls. The co-location note exists so unit-test monkeypatching of `owui_get_last_response` targets the module the driver actually calls.

## Interfaces

The OWUI REST helpers including `owui_get_last_response` and the archival functions.

## Gotchas

Monkeypatch `tests.uat.owui_api.owui_get_last_response` — that is the exact function the driver calls.
