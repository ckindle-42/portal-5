---
id: unit-PERSONA_MATRIX_CI-out-of-scope-for-ci
kind: why
title: "PERSONA_MATRIX_CI \u2014 Out of scope for CI"
sources:
- type: design
  path: docs/PERSONA_MATRIX_CI.md
  section: Out of scope for CI
last_generated_commit: ''
confidence: high
tags:
- docs
- PERSONA_MATRIX_CI
created_at: 1783195000.883301
updated_at: 1783195000.883301
---


- TPS / latency comparison. That's `bench_tps`'s job; the matrix only
  cares about behavioral pass/fail.
- Pipeline routing tests. Acceptance v6 covers those (`S3a` / `S3b`).
- Per-(persona, model) coverage of non-registered workspaces. Each
  workspace must register in `WORKSPACE_REGISTRY` before CI can sweep it.
