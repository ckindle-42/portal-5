---
id: unit-uat-catalog-g_auto_creative
kind: mixed
title: "UAT catalog group \u2014 auto-creative"
sources:
- type: code
  path: tests/uat_catalog/g_auto_creative.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.804703
updated_at: 1785800128.804703
---

This catalog group covers the auto-creative workspace(s), exporting a `TESTS`
list of 3 UAT tests across the auto-creative section(s).

## Why

Its tests cover constrained flash fiction, deliberate-choice writing, and character consistency across the creative personas. These assert the creative tier's discipline — structure and voice — rather than just that a story is produced.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
