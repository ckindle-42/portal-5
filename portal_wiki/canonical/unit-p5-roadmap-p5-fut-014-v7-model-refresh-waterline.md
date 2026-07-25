---
id: unit-p5-roadmap-p5-fut-014-v7-model-refresh-waterline
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-014-V7: Model Refresh Waterline"
sources:
- type: doc
  path: P5_ROADMAP.md
  commit: 05e42ec2
  section: 'P5-FUT-014-V7: Model Refresh Waterline'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.592656
updated_at: 1784946220.592656
---

TASK_MODEL_REFRESH_V7 (2026-05-27) added 6 bench workspaces (one since
removed from the fleet): bench-voxtral-realtime, bench-voxtral-tts,
bench-granite-speech, bench-qwen36-27b-ud, bench-qwen36-35b-a3b-ud.

**Promotion gates** (each model is bench-only until):

1. `bench-qwen36-{27b,35b-a3b}-ud` → replace stock 4-bit in respective
   bench pins: must show ≥1-point improvement on Creative Coder CC-01
   AND match-or-improve coding-shootout-v2.
2. `bench-granite-speech` → new `auto-transcribe-domain` lane: must
   outperform mlx-whisper-large-v3-turbo on a domain-vocab keyword-biased
   benchmark.
3. `bench-voxtral-realtime` / `bench-voxtral-tts` → defer to dedicated
   P5-FUT-SPEECH-002 speech-shootout task.

---
