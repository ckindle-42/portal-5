---
id: unit-sec-core-notify_scoreboard
kind: mixed
title: "Notify scoreboard \u2014 hunt-and-notify semantics"
sources:
- type: code
  path: portal/modules/security/core/notify_scoreboard.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800295.902841
updated_at: 1785800295.902841
---

The hunt-and-notify scoreboard: the semantics that govern when a hunt is scored as notifying correctly, and the scoreboard that tracks it.

## Why

A hunt-and-notify capability is only useful if the notification semantics are well-defined — when does a hunt count as having notified, and when is that a false alarm? The scoreboard encodes those semantics and tracks the outcomes, which is what the alert-fatigue and scoreboard gates assert.

## Interfaces

The hunt-and-notify scoreboard: the semantics that govern when a hunt is scored as notifying correctly, and the scoreboard that tracks it lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
