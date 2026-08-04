---
id: unit-sec-core-episode
kind: mixed
title: "Episode \u2014 deterministic purple-run record"
sources:
- type: code
  path: portal/modules/security/core/episode.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394163
updated_at: 1785800269.394163
---

One episode per purple run, deterministic — no model touches it.

## Why

The episode record must be a faithful record of what happened, which is why no model touches it — a model-influenced episode could retroactively justify a wrong decision. Determinism is what makes the record trustworthy as evidence.

## Interfaces

One episode per purple run, deterministic — no model touches it lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
