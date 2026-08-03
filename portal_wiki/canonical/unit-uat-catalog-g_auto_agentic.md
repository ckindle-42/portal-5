---
id: unit-uat-catalog-g_auto_agentic
kind: mixed
title: "UAT catalog group \u2014 auto-agentic (heavy)"
sources:
- type: code
  path: tests/uat_catalog/g_auto_agentic.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.804686
updated_at: 1785800128.804686
---

This catalog group covers the auto-agentic (heavy) workspace(s), exporting a `TESTS`
list of 2 UAT tests across the auto-agentic section(s).

## Why

Its tests are the heaviest coding workload in the catalog: a full Flask migration plan and a codebase-wiki inference task. These exercise the tool-loop-heavy agentic path where a model must plan and execute multi-step coding work, which the lighter auto and auto-coding groups do not stress.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
