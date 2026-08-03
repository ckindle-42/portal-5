---
id: unit-acceptance-s23_model_diversity
kind: mixed
title: "S23 \u2014 Model diversity"
sources:
- type: code
  path: tests/acceptance/s23_model_diversity.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799805.13595
updated_at: 1785799805.13595
---

This is the acceptance section s23_model_diversity. S23 — Model diversity

## Why

It verifies the fleet serves diverse model families. A backend collapse that serves one model for every workspace is a silent capability regression — the fleet looks healthy until a persona asks for a capability only a missing family provides, which is what this section catches.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
