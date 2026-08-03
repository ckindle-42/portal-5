---
id: unit-uat-catalog-g_auto_spl
kind: mixed
title: "UAT catalog group \u2014 auto-spl"
sources:
- type: code
  path: tests/uat_catalog/g_auto_spl.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.8047202
updated_at: 1785800128.8047202
---

This catalog group covers the auto-spl workspace(s), exporting a `TESTS`
list of 2 UAT tests across the auto-spl section(s).

## Why

Its tests cover the SPL workspace: refactoring a slow search and redirecting a non-SPL request. The redirect test is the discipline assertion — the SPL workspace must refuse to answer what is not an SPL question.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
