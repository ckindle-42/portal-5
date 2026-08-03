---
id: unit-uat-catalog-g_auto_redteam_deep
kind: mixed
title: "UAT catalog group \u2014 auto-redteam-deep"
sources:
- type: code
  path: tests/uat_catalog/g_auto_redteam_deep.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.804717
updated_at: 1785800128.804717
---

This catalog group covers the auto-redteam-deep workspace(s), exporting a `TESTS`
list of 2 UAT tests across the auto-security (redteam-deep) section(s).

## Why

Its tests cover the deep red-team workspace: high-fidelity ATT&CK analysis and a NERC CIP threat simulation. These assert the deep offensive tier's fidelity to the ATT&CK and CIP taxonomies.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
