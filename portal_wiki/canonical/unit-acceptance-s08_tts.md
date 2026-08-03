---
id: unit-acceptance-s08_tts
kind: mixed
title: "S8 \u2014 Text-to-speech"
sources:
- type: code
  path: tests/acceptance/s08_tts.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799764.058754
updated_at: 1785799764.058754
---

This is the acceptance section s08_tts. S8 — Text-to-speech

## Why

It proves the TTS service synthesises real audio. A speech persona that returns silence or text instead of a playable file is a silent failure, and the audio-format validation here is what catches it.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
