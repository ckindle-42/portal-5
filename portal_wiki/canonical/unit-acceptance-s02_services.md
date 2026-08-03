---
id: unit-acceptance-s02_services
kind: mixed
title: "S2 \u2014 Service health"
sources:
- type: code
  path: tests/acceptance/s02_services.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799745.5236712
updated_at: 1785799745.5236712
---

This is the acceptance section s02_services. S2 — Service health

## Why

It verifies that the required services are up before any section drives them. A service that is down must not be allowed to masquerade as a model or routing failure in a later section — separating service availability from behaviour is what keeps a single dead service from producing dozens of misleading section failures.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
