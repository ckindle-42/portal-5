---
id: unit-uat-catalog-g_auto_video
kind: mixed
title: "UAT catalog group \u2014 auto-video"
sources:
- type: code
  path: tests/uat_catalog/g_auto_video.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.8047218
updated_at: 1785800128.8047218
---

This catalog group covers the auto-video workspace(s), exporting a `TESTS`
list of 2 UAT tests across the auto-video section(s).

## Why

Its tests cover a video creator request (storm timelapse) and an image-generation request through ComfyUI FLUX. The pair asserts both generation families the media tier serves.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
