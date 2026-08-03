---
id: unit-uat-catalog-g_tools_specialist
kind: mixed
title: "UAT catalog group \u2014 tools-specialist"
sources:
- type: code
  path: tests/uat_catalog/g_tools_specialist.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.804725
updated_at: 1785800128.804725
---

This catalog group covers the tools-specialist workspace(s), exporting a `TESTS`
list of 5 UAT tests across the tools-specialist section(s).

## Why

Its tests cover the tool-composer workspace: a multi-step tool plan and the execute_bash, execute_nodejs, and execute_python tool-validation proofs plus the file-count persona test. The validation tests are the tool-tier contract — each sandbox executor must actually run and return a real result.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
