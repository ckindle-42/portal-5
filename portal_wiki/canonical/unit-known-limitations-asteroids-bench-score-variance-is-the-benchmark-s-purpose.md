---
id: unit-known-limitations-asteroids-bench-score-variance-is-the-benchmark-s-purpose
kind: what
title: "KNOWN_LIMITATIONS \u2014 Asteroids Bench Score Variance Is the Benchmark's\
  \ Purpose"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/personas/bench_granite41_8b.yaml
- type: code
  path: tests/benchmarks/bench/prompts.py
last_generated_commit: 1ed83b22525c97ed996c835b7519e10c75d13ad0
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.666697
updated_at: 1784946220.666697
---

- **ID**: P5-BENCH-001
- **Description**: The CC-01 Asteroids challenge is the creative-coding benchmark wired across the `bench-` workspaces in `config/portal.yaml`, one identical task per model (ship rotation, thrust, bullet fire, asteroid split, level advance). The bench persona catalog (`config/personas/`) shares a single `prompt_template: creative_coder`, and `tests/benchmarks/bench/prompts.py` documents that CC-01 deliberately uses the coding category so cross-bench numbers stay comparable even though creative coding is not every model's strength. Score variance on the fixed task is therefore the benchmark's purpose: it reflects model capability, not a test harness defect.
- **Operator action**: Use bench scores as model-selection signal. A low CC-01 score against a reasoning-heavy model is expected, not a defect; a model that cannot clear a basic creative-coding bar should not be promoted into HTML-generation routing.

## Why

Benchmark workspaces exist to isolate model capability from routing and harness noise, so the corpus and prompt must be held fixed across every candidate. If each bench persona carried its own system prompt, score deltas would be unreadable as model signal. Keeping one `creative_coder` template and one task makes the output comparable, and the documented category assignment prevents a low score from being misread as a regression.
