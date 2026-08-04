---
id: unit-uat-catalog-g_auto_coding_agentic
kind: mixed
title: "UAT catalog group \u2014 auto-coding agentic"
sources:
- type: code
  path: tests/uat_catalog/g_auto_coding_agentic.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800012.7221918
updated_at: 1785800012.7221918
---

This catalog group covers the auto-coding agentic workspace(s), exporting a `TESTS`
list of 4 UAT tests across the auto-coding agentic variants section(s).

## Why

The group exists because the UAT catalog was a single inline structure that
was impractical to edit, and splitting it per workspace is what made the
catalog maintainable. Each group is the authoritative test set for its
workspace: the tests drive the live stack against that workspace's routing,
serving, and capability assertions. The coding-agentic group covers the agentic coding variants (laguna, lite, uncensored-agentic), testing the tool-loop-heavy coding path.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
