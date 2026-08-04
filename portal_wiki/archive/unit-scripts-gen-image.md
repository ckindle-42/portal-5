---
id: unit-scripts-gen-image
kind: mixed
title: "Script \u2014 gen-image"
sources:
- type: code
  path: scripts/gen-image.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799510.578014
updated_at: 1785799510.578014
---

Generates images through the ComfyUI pipeline from the command line, handling the API workflow submission and result retrieval.

## Why

An operator needs a direct CLI path to image generation for testing and scripting, and the script wraps the ComfyUI workflow submission so the generation call is repeatable from the shell rather than through the chat interface.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
