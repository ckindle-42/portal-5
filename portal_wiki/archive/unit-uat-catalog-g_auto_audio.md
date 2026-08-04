---
id: unit-uat-catalog-g_auto_audio
kind: mixed
title: "UAT catalog group \u2014 auto-audio"
sources:
- type: code
  path: tests/uat_catalog/g_auto_audio.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.804692
updated_at: 1785800128.804692
---

This catalog group covers the auto-audio workspace(s), exporting a `TESTS`
list of 2 UAT tests across the auto-audio section(s).

## Why

Its tests ask the audio-analyst workspace for a capabilities overview and a meeting summary — the two audio-domain requests that exercise whether the workspace routes to the audio tier and serves coherent audio-domain prose rather than a generic answer.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
