---
id: unit-persona-matrix-ci-out-of-scope-for-ci
kind: what
title: "PERSONA_MATRIX_CI \u2014 Out of scope for CI"
sources:
- type: doc
  path: docs/PERSONA_MATRIX_CI.md
  commit: 05e42ec2
  section: Out of scope for CI
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.569539
updated_at: 1784946220.569539
---

- TPS / latency comparison. That's `bench_tps`'s job; the matrix only
  cares about behavioral pass/fail.
- Pipeline routing tests. Acceptance v6 covers those (`S3a` / `S3b`).
- Per-(persona, model) coverage of non-registered workspaces. Each
  workspace must register in `WORKSPACE_REGISTRY` before CI can sweep it.
