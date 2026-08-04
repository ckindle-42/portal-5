---
id: unit-uat-catalog-g_auto_purpleteam_deep
kind: mixed
title: "UAT catalog group \u2014 auto-purpleteam-deep"
sources:
- type: code
  path: tests/uat_catalog/g_auto_purpleteam_deep.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.804713
updated_at: 1785800128.804713
---

This catalog group covers the auto-purpleteam-deep workspace(s), exporting a `TESTS`
list of 1 UAT tests across the auto-security (purpleteam-deep) section(s).

## Why

Its single test is the four-hop chain from phishing to an IR playbook — the deepest multi-hop security workload in the catalog. One test, but it is the full-chain assertion no shorter test can make.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
