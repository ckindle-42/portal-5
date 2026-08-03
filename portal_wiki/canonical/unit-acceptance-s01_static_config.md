---
id: unit-acceptance-s01_static_config
kind: mixed
title: "S1 \u2014 Configuration consistency"
sources:
- type: code
  path: tests/acceptance/s01_static_config.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799741.797813
updated_at: 1785799741.797813
---

This is the acceptance section s01_static_config. S1 — Configuration consistency

## Why

It checks that the configuration surface is internally consistent — workspace ids resolve, persona parents exist, backend references point at real entries. A contradiction in config is the cheapest failure to catch because every later section depends on the same config, and a config error that survives to the runtime sections produces failures that look like the services rather than the file. Running this first is what makes a config regression attributable.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
