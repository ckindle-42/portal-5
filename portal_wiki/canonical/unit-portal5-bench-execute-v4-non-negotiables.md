---
id: unit-portal5-bench-execute-v4-non-negotiables
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Non-negotiables"
sources:
- type: code
  path: scripts/execute_preflight.py
- type: code
  path: tests/benchmarks/bench/cli.py
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.703862
updated_at: 1784946220.703862
---

- Preflight + `--dry-run` before every run; counts come from there, not this
  doc.
- `PORTAL_ENABLE_EVAL=1` for full coverage of the eval-module workspaces.
- Product code is read-only; bench failures that are product bugs get
  reported.
- Every run fresh; no prior-run assumptions.

## Why

These rules exist because the bench's inputs are config-driven and its results
are only trustworthy if the surface being tested is canonical and complete.
The preflight and `--dry-run` recompute scale from `config/portal.yaml` and
`config/backends.yaml` at run time, so trusting them instead of a doc prevents
stale-plan errors. `PORTAL_ENABLE_EVAL=1` mirrors the eval-module opt-in that
the pipeline enforces at boot, and the read-only rule keeps the bench a
measurement instrument rather than a place to patch routing bugs.
