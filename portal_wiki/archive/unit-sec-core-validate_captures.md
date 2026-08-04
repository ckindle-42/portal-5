---
id: unit-sec-core-validate_captures
kind: mixed
title: "Validate captures \u2014 VALID/PARTIAL/INVALID/MISSING"
sources:
- type: code
  path: portal/modules/security/core/validate_captures.py
  commit: 11d83e41
last_generated_commit: 11d83e41
claims: []
confidence: high
tags:
- authored-v1
- module
- security
created_at: 1785800269.394173
updated_at: 1785800269.394173
---

Classifies every scenario capture as VALID, PARTIAL, INVALID, or MISSING and writes the recapture-needed list.

## Why

A bench that runs against a partial or invalid capture produces numbers that look real. The classifier grades every capture so an operator knows which scenarios produced trustworthy evidence and which need recapture before the bench is believed.

## Interfaces

Classifies every scenario capture as VALID, PARTIAL, INVALID, or MISSING and writes the recapture-needed list lives in the security core package and is consumed by the engagement machinery and the bench.

## Gotchas

As part of the RBP engine, changes here must respect the module's internal wiring — the core was relocated intact, so its dependencies and re-export contracts are load-bearing.
