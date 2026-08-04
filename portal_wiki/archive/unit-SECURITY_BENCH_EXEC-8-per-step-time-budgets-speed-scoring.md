---
id: unit-SECURITY_BENCH_EXEC-8-per-step-time-budgets-speed-scoring
kind: why
title: "SECURITY_BENCH_EXEC \u2014 8. Per-Step Time Budgets + Speed Scoring"
sources:
- type: design
  path: docs/SECURITY_BENCH_EXEC.md
  section: 8. Per-Step Time Budgets + Speed Scoring
last_generated_commit: ''
confidence: high
tags:
- docs
- SECURITY_BENCH_EXEC
created_at: 1783195000.9032938
updated_at: 1783195000.9032938
---

Each step has a `time_budget_s` field (e.g., recon=60s, kerberoast=120s, crack=300s). `speed_score` = fraction of steps that completed within budget. Displayed as `speed=0.67` in the chain summary.
