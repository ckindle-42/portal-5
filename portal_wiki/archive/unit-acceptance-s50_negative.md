---
id: unit-acceptance-s50_negative
kind: mixed
title: "S50 \u2014 Negative tests"
sources:
- type: code
  path: tests/acceptance/s50_negative.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799827.616645
updated_at: 1785799827.616645
---

This is the acceptance section s50_negative. S50 — Negative tests

## Why

It verifies the pipeline refuses what it should — bad auth, bad inputs, unsupported cases. A pipeline that accepts bad auth or silently passes malformed input has failed its admission contract even if every positive test passes, which is why the negative suite exists.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
