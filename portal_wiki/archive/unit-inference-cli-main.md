---
id: unit-inference-cli-main
kind: mixed
title: "Inference CLI main \u2014 python -m entry delegate"
sources:
- type: code
  path: portal/platform/inference/cli/__main__.py
  commit: 5fbf51f8
last_generated_commit: 5fbf51f8
claims: []
confidence: high
tags:
- authored-v1
- platform
- cli
created_at: 1785797827.404568
updated_at: 1785797827.404568
---

This is the `python -m portal.platform.inference.cli` entry point: it
delegates to the CLI package's root app.

## Why

A module entry point is what makes `python -m` work from a bare interpreter,
and keeping it as a three-line delegate means the app definition lives in one
place (the package `__init__`) rather than split between the package and the
entry.

## Interfaces

Imports `app` from the package and runs it under `__main__`.
