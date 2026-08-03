---
id: unit-acceptance-s07_music
kind: mixed
title: "S7 \u2014 Music generation"
sources:
- type: code
  path: tests/acceptance/s07_music.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799760.350872
updated_at: 1785799760.350872
---

This is the acceptance section s07_music. S7 — Music generation

## Why

It proves the music workspace produces a real audio artifact. Music generation is a long-running workload, so its section also exercises the wait-for-completion path that the shared infrastructure provides.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
