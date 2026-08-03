---
id: unit-uat-catalog-g_auto_voice
kind: mixed
title: "UAT catalog group \u2014 auto-voice"
sources:
- type: code
  path: tests/uat_catalog/g_auto_voice.py
  commit: 832db546
last_generated_commit: 832db546
claims: []
confidence: high
tags:
- authored-v1
- tests
- uat-catalog
created_at: 1785800140.325577
updated_at: 1785800140.325577
---

This catalog group covers the auto-voice workspace, exporting a `TESTS`
list of 1 UAT test across the auto-music section.

## Why

Its single test is the Whisper STT voice-to-text round-trip. One test, but it
is the speech-to-text tier's proof that a recorded voice actually returns a
transcription — without it, a regression in the STT path could go unnoticed
because no other catalog group exercises the speech-to-text direction.

## Interfaces

Exports `TESTS`, a list of test dicts (id, name, section, model_slug,
timeout, workspace_tier, prompt, assertions) consumed by the catalog
concatenation and the runner.

## Gotchas

The test dicts reference assertion sets from `_shared` and section ids the
runner recognises — a group that introduces a new section id must be wired
into the runner's section handling or its tests silently skip.
