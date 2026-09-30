---
id: unit-acceptance-s15_shared_workspace
kind: mixed
title: "S15 \u2014 Shared workspace"
sources:
- type: code
  path: tests/acceptance/s15_shared_workspace.py
  commit: e75dddd2
last_generated_commit: e75dddd2
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799786.3982668
updated_at: 1785799786.3982668
---

This is the acceptance section s15_shared_workspace. S15 — Shared workspace

## Why

It verifies the shared workspace paths resolve and are writable, the Rule 11 contract that user files live at one root visible to every service. A workspace that is not actually shared would strand generated artifacts where other services cannot reach them, which is the failure this section prevents.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
