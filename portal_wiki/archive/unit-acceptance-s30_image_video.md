---
id: unit-acceptance-s30_image_video
kind: mixed
title: "S30 \u2014 Image and video"
sources:
- type: code
  path: tests/acceptance/s30_image_video.py
  commit: a88ad75b
last_generated_commit: a88ad75b
claims: []
confidence: high
tags:
- authored-v1
- tests
- acceptance
created_at: 1785799808.909462
updated_at: 1785799808.909462
---

This is the acceptance section s30_image_video. S30 — Image and video

## Why

It proves the image and video generation paths produce real artifacts. Generation is the heaviest workload family, and this section verifies both the image and the video paths render actual output files.

## Interfaces

The section drives the live stack (pipeline, services, or MCP bridges) and records PASS/WARN/FAIL outcomes through the shared result surface.

## Gotchas

Like every section, it requires the live stack — its failures mean the stack or the configuration is broken, not the test.
