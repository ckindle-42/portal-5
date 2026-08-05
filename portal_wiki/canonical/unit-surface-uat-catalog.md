---
id: unit-surface-uat-catalog
kind: mixed
title: "UAT scenario catalog \u2014 data modules, assembly order, shared vocabulary"
sources:
- type: code
  path: tests/uat_catalog/*.py
last_generated_commit: 863d7aa3152e7562e2d09344959c464b20eec0de
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat
created_at: 1785882600.0
updated_at: 1785882600.0
---

The UAT scenario catalog is a package of independent data modules. Each group module exports a `TESTS` list for one workspace family, and the package entrypoint concatenates those lists into `TEST_CATALOG`.

## Why

The catalog began as a single inline structure inside the UAT driver that was impractical to edit. Splitting it per workspace makes adding a workspace's tests a one-file change: create a group module with a `TESTS` list and append its import to `_GROUPS`. Import order is load-bearing, not cosmetic — the concatenated list is the stable pre-sort order `sort_tests_cascade` consumes before cascade reordering, so a misplaced import silently reshuffles what the runner sees. The `_shared` module exists so the grading vocabulary is defined once and imported, never duplicated per group.

## Interfaces

The package exposes `TEST_CATALOG`, built by extending it with each group's `TESTS` in `_GROUPS` order. Groups import their assertion and refusal vocabulary from `_shared` — `REFUSAL_PHRASES`, `_CC01_ASSERTIONS`, `_CC01_ASSERTIONS_BENCH`. A test dict carries `id`, `name`, `section`, `model_slug`, `timeout`, `workspace_tier`, `prompt`, and `assertions`.

## Gotchas

Section selection filters on the exact string value, so a section id that no group wires into the runner's selection surface is unreachable and its tests skip without warning. The `_shared` assertion sets are the grading contract every group references — changing one changes what every group asserts. Append new groups to `_GROUPS` at the correct position; the pre-sort order depends on it.
