---
id: unit-uat-catalog-g_auto_compliance
kind: mixed
title: "UAT catalog group \u2014 auto-compliance"
sources:
- type: code
  path: tests/uat_catalog/g_auto_compliance.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.804699
updated_at: 1785800128.804699
---

This catalog group covers the auto-compliance workspace(s), exporting a `TESTS`
list of 3 UAT tests across the auto-compliance section(s).

## Why

Its tests are NERC CIP focused: a CIP-003-9 citation, an aspirational-language rejection check, and the compliance-analyst workspace request. The aspirational-rejection test is the methodology assertion — a compliant persona must refuse language that asserts a posture it does not mandate.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
