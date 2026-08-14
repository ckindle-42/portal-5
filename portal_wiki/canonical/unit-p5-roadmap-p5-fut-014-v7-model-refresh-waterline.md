---
id: unit-p5-roadmap-p5-fut-014-v7-model-refresh-waterline
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-014-V7: Model Refresh Waterline"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: config/backends.yaml
- type: code
  path: CHANGELOG.md
- type: code
  path: tests/uat_catalog/g_benchmark.py
- type: code
  path: tests/benchmarks/coding_shootout_analyze.py
last_generated_commit: aae69a16de501e8524f279c9bff13f3fdc241f32
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.592656
updated_at: 1784946220.592656
---

TASK_MODEL_REFRESH_V7 (2026-05-27, recorded in `CHANGELOG.md`) added six bench
workspaces to the fleet. Two survive in current config:
`bench-qwen36-27b-ud` (in `config/portal.yaml`, `model_hint` qwen3.6:27b-q4_K_M,
described as a proxy for the not-yet-pulled Unsloth UD quant) and
`bench-qwen36-35b-a3b-ud` (`model_hint`
`hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_XL`, agentic-lane candidate C1) —
both under `module: eval` and gated for promotion (`PROMOTE_POLICY=confirm` in
`config/backends.yaml`). The three speech candidates from the same intake —
bench-voxtral-realtime, bench-voxtral-tts, bench-granite-speech — are not
registered in `config/portal.yaml` and survive only as CHANGELOG records. The
promotion gates the roadmap lists have code anchors: the CC-01 Asteroids coding
challenge shootout lives in `tests/uat_catalog/g_benchmark.py` and the
coding-shootout-v2 analyzer in `tests/benchmarks/coding_shootout_analyze.py`.

## Why

This unit records which V7 bench candidates actually shipped as config versus
which were aspirational or already removed. `config/portal.yaml` is the single
source of truth for what the fleet serves, so the two surviving UD workspaces
and the absence of the speech bench entries are the facts this unit asserts; the
promotion gates are future intent, anchored only to the benchmark harnesses that
would measure them.
