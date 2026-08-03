---
id: unit-acceptance-s00_startup
kind: mixed
title: "S0 \u2014 Prerequisites and environment check"
sources:
- type: code
  path: tests/acceptance/s00_startup.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799713.799298
updated_at: 1785799713.799298
---

This is the acceptance section s00_startup. S0 — Prerequisites and environment check

## Why

It verifies the preconditions every later section assumes: the environment, the services, and the config are present before any test runs. A section that assumes a running stack that was never confirmed produces a failure that looks like the test when it is actually the prerequisites.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
