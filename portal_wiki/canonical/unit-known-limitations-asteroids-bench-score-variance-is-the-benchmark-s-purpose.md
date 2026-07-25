---
id: unit-known-limitations-asteroids-bench-score-variance-is-the-benchmark-s-purpose
kind: what
title: "KNOWN_LIMITATIONS \u2014 Asteroids Bench Score Variance Is the Benchmark's\
  \ Purpose"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: Asteroids Bench Score Variance Is the Benchmark's Purpose
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.666697
updated_at: 1784946220.666697
---

- **ID**: P5-BENCH-001
- **Description**: The CC-01 Asteroids bench (`bench-*` workspaces) intentionally surfaces raw model differences on a fixed task. All bench personas share an identical creative-coder system prompt — score variance reflects model capability, not a test harness defect.
- **Operator action**: Use bench scores as model-selection signal. A model scoring ≤3/5 on CC-01 is not a candidate for `auto-coding` HTML generation tasks.
