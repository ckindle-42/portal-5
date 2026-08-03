---
id: unit-acceptance-s70_information_access
kind: mixed
title: "S70 \u2014 Information access"
sources:
- type: code
  path: tests/acceptance/s70_information_access.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799835.091163
updated_at: 1785799835.091163
---

This is the acceptance section s70_information_access. S70 — Information access

## Why

It exercises the information-access paths such as attachments and context injection, proving the grounding surface serves. The grounding paths are what make the pipeline's answers informed, and a regression in injection would silently degrade every grounded response.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
