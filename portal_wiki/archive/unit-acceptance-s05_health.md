---
id: unit-acceptance-s05_health
kind: mixed
title: "S5 \u2014 Health endpoints"
sources:
- type: code
  path: tests/acceptance/s05_health.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799752.92168
updated_at: 1785799752.92168
---

This is the acceptance section s05_health. S5 — Health endpoints

## Why

It verifies the health endpoints report correctly. Health is the baseline signal of stack coherence — a pipeline whose health endpoint lies is a pipeline whose other failures cannot be trusted either, so the health contract is checked before the behavioural sections rely on it.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
