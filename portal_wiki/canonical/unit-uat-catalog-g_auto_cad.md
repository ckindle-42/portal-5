---
id: unit-uat-catalog-g_auto_cad
kind: mixed
title: "UAT catalog group \u2014 auto-cad"
sources:
- type: code
  path: tests/uat_catalog/g_auto_cad.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.804697
updated_at: 1785800128.804697
---

This catalog group covers the auto-cad workspace(s), exporting a `TESTS`
list of 5 UAT tests across the auto-cad section(s).

## Why

Its tests span the CAD surface: parametric bracket and hex-enclosure modelling, STL-to-OBJ conversion, and the designer and printability-engineer personas. The mix of workspace-level generation and persona-level analysis is what makes this group cover the CAD tier both as a tool and as a discipline.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
