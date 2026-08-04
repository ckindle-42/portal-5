---
id: unit-acceptance-s10c_compliance_personas
kind: mixed
title: "S10c \u2014 Compliance personas"
sources:
- type: code
  path: tests/acceptance/s10c_compliance_personas.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799775.231172
updated_at: 1785799775.231172
---

This is the acceptance section s10c_compliance_personas. S10c — Compliance personas

## Why

It exercises the compliance personas and their structural assertions. Compliance is methodology-bound, so the section verifies the mandated output structure (columns, classification tokens, refusal phrases) rather than volatile values, proving the compliance tier serves its methodology.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
