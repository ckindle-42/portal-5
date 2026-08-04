---
id: unit-sec-core-response_loop
kind: mixed
title: "Response loop \u2014 stay-current-by-construction"
sources:
- type: code
  path: portal/modules/security/core/response_loop.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.39417
updated_at: 1785800269.39417
---

Phase 7 of the RBP build: closes the fourth loop (response) and makes the system stay current by construction.

## Why

The response loop is what makes the system update itself — new detections and scenarios feed back so the capability surface stays current without manual curation. The by-construction property is the point: currency is an emergent result of the loop, not a maintenance task.

## Interfaces

Phase 7 of the RBP build: closes the fourth loop (response) and makes the system stay current by construction lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
