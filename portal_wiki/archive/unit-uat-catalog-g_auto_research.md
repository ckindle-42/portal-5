---
id: unit-uat-catalog-g_auto_research
kind: mixed
title: "UAT catalog group \u2014 auto-research"
sources:
- type: code
  path: tests/uat_catalog/g_auto_research.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.804718
updated_at: 1785800128.804718
---

This catalog group covers the auto-research workspace(s), exporting a `TESTS`
list of 4 UAT tests across the auto-research section(s).

## Why

Its tests cover the research workspace and its personas: post-quantum cryptography, evidence-quality labelling, an evidence-framework regulation answer, and an adversarial-ML analysis. The evidence-labelling tests are the research tier's grounding contract — research answers must be graded on their evidence, not their confidence.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
