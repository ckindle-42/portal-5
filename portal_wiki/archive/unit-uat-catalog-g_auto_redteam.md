---
id: unit-uat-catalog-g_auto_redteam
kind: mixed
title: "UAT catalog group \u2014 auto-redteam"
sources:
- type: code
  path: tests/uat_catalog/g_auto_redteam.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.804715
updated_at: 1785800128.804715
---

This catalog group covers the auto-redteam workspace(s), exporting a `TESTS`
list of 3 UAT tests across the auto-redteam section(s).

## Why

Its tests cover the red-team workspace: an AD pivot, an OT physical-risk flag, and scope confirmation. The physical-risk flag is the safety assertion — a red-team persona must surface real-world hazard even inside a simulated engagement.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
