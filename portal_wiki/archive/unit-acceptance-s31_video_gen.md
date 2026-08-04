---
id: unit-acceptance-s31_video_gen
kind: mixed
title: "S31 \u2014 Video generation"
sources:
- type: code
  path: tests/acceptance/s31_video_gen.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799812.628774
updated_at: 1785799812.628774
---

This is the acceptance section s31_video_gen. S31 — Video generation

## Why

It proves the video generation path specifically, the heaviest generation workload. Video is the longest and most memory-intensive generation, so its section isolates the video path where a memory or queue-management regression shows first.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
