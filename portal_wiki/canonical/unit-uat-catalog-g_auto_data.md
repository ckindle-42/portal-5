---
id: unit-uat-catalog-g_auto_data
kind: mixed
title: "UAT catalog group \u2014 auto-data"
sources:
- type: code
  path: tests/uat_catalog/g_auto_data.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.804706
updated_at: 1785800128.804706
---

This catalog group covers the auto-data workspace(s), exporting a `TESTS`
list of 7 UAT tests across the auto-data section(s).

## Why

Its tests cover the data-analyst workspace and its data personas: dataset cleaning, correlation-vs-causation, imbalanced-class handling, benchmark-vs-production, assumption-checking before a t-test, and a pandas aggregation. The statistical-rigour assertions are what distinguish this group — the data tier is scored on method, not just answers.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
