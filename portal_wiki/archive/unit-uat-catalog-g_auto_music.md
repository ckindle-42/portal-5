---
id: unit-uat-catalog-g_auto_music
kind: mixed
title: "UAT catalog group \u2014 auto-music"
sources:
- type: code
  path: tests/uat_catalog/g_auto_music.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800128.8047092
updated_at: 1785800128.8047092
---

This catalog group covers the auto-music workspace(s), exporting a `TESTS`
list of 2 UAT tests across the auto-music section(s).

## Why

Its tests cover dark-ambient music generation and a British-voice TTS request. Two short tests, but they are the audio-tier's generation proof — the music workspace must produce a playable artifact and the TTS path must speak in the requested voice.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
