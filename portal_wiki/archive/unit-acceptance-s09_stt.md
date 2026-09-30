---
id: unit-acceptance-s09_stt
kind: mixed
title: "S9 \u2014 Speech-to-text"
sources:
- type: code
  path: tests/acceptance/s09_stt.py
  commit: e75dddd2
last_generated_commit: e75dddd2
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799767.810996
updated_at: 1785799767.810996
---

This is the acceptance section s09_stt. S9 — Speech-to-text

## Why

It proves the STT service transcribes real audio, exercising both the plain and the diarized transcription paths. Transcription is the reverse direction of the speech tier, and a regression that breaks one direction while leaving the other working is exactly what this section isolates.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
