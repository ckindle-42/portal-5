---
id: unit-acceptance-s41_production_hardening
kind: mixed
title: "S41 \u2014 Production hardening"
sources:
- type: code
  path: tests/acceptance/s41_production_hardening.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799820.1734688
updated_at: 1785799820.1734688
---

This is the acceptance section s41_production_hardening. S41 — Production hardening

## Why

It verifies the production-hardening properties: auth, concurrency limits, and the admission controls that keep the pipeline safe under load. These are the properties that fail only under pressure, so a dedicated section that exercises them is what catches a hardening regression before it reaches a real load spike.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
