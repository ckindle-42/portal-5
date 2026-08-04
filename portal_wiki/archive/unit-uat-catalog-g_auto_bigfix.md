---
id: unit-uat-catalog-g_auto_bigfix
kind: mixed
title: "UAT catalog group \u2014 auto-bigfix"
sources:
- type: code
  path: tests/uat_catalog/g_auto_bigfix.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.8046951
updated_at: 1785800128.8046951
---

This catalog group covers the auto-bigfix workspace(s), exporting a `TESTS`
list of 2 UAT tests across the auto-bigfix section(s).

## Why

Its tests cover the BigFix patch-management domain: writing a relevance-language expression and a REST API patch-compliance query. These probe the workspace's specialised endpoint-management vocabulary, which no other group exercises.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
