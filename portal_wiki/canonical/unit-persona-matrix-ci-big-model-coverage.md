---
id: unit-persona-matrix-ci-big-model-coverage
kind: what
title: "PERSONA_MATRIX_CI \u2014 Big-model coverage"
sources:
- type: doc
  path: docs/PERSONA_MATRIX_CI.md
  commit: 05e42ec2
  section: Big-model coverage
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5688782
updated_at: 1784946220.5688782
---

Models flagged `big_model: true` in `backends.yaml` (currently:
`Qwen3-Coder-Next-4bit` ~46GB, `Llama-3.3-70B-Instruct-4bit` ~40GB,
`Qwen3-VL-32B-Instruct-8bit` ~36GB) are skipped from CI by default.
Each big-model load takes 1–3 minutes plus full eviction of every other
model — running them in a nightly sweep would extend the workflow past
its 120-minute timeout.

Big-model coverage is operator-driven:
- Pre-release validation: run `--include-big-models` once before
  shipping a release that touches the agentic-coding workspace.
- Quarterly: same trigger as re-baselining.
