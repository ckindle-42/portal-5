---
id: unit-uat-catalog-g_auto_reasoning
kind: mixed
title: "UAT catalog group \u2014 auto-reasoning"
sources:
- type: code
  path: tests/uat_catalog/g_auto_reasoning.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.804714
updated_at: 1785800128.804714
---

This catalog group covers the auto-reasoning workspace(s), exporting a `TESTS`
list of 6 UAT tests across the auto-reasoning and GLM thinking section(s).

## Why

Its tests cover the reasoning workspace and its personas: a secrets-management trade-off, consult-before-design, requirements-before-architecture, rate-limiting trade-offs, an independent second opinion, and a multi-step GLM thinking problem. The persona tests assert *process* — reasoning before answering — which is the reasoning tier's defining behaviour.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
