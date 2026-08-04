---
id: unit-uat-catalog-g_auto_daily
kind: mixed
title: "UAT catalog group \u2014 auto-daily"
sources:
- type: code
  path: tests/uat_catalog/g_auto_daily.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.8047051
updated_at: 1785800128.8047051
---

This catalog group covers the auto-daily workspace(s), exporting a `TESTS`
list of 15 UAT tests across the auto-daily section(s).

## Why

Its fifteen tests are the catalog's broadest workspace sweep: casual chat with no reasoning leak, summarization, planning, git-safety, escalation honesty, memory-augmented and web-search variants, and end-to-end document plus multi-tool chains. The daily workspace is the general-purpose surface, so this group is where a general regression shows first.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
