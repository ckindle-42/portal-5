---
id: unit-scripts-gen-video
kind: mixed
title: "Script \u2014 gen-video"
sources:
- type: code
  path: scripts/gen-video.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799514.2111192
updated_at: 1785799514.2111192
---

Generates video through the ComfyUI pipeline from the command line.

## Why

The video generation path is the heaviest ComfyUI workload, and a CLI wrapper makes it scriptable and repeatable for the benches and tests that need actual generated video.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
