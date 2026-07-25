---
id: unit-portal5-bench-execute-v4-non-negotiables
kind: what
title: "PORTAL5_BENCH_EXECUTE_V4 \u2014 Non-negotiables"
sources:
- type: doc
  path: tests/PORTAL5_BENCH_EXECUTE_V4.md
  commit: 05e42ec2
  section: Non-negotiables
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.703862
updated_at: 1784946220.703862
---

- Preflight + `--dry-run` before every run; counts come from there, not this doc.
- `PORTAL_ENABLE_EVAL=1` for full coverage.
- Product code is read-only; bench failures that are product bugs get reported.
- Every run fresh; no prior-run assumptions.
