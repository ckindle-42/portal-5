---
id: unit-p5-roadmap-p5-fut-speech-002-speech-model-shootout
kind: what
title: "P5_ROADMAP \u2014 P5-FUT-SPEECH-002: Speech-Model Shootout"
sources:
- type: doc
  path: P5_ROADMAP.md
  commit: 05e42ec2
  section: 'P5-FUT-SPEECH-002: Speech-Model Shootout'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5934029
updated_at: 1784946220.5934029
---

Current production speech stack: mlx-transcribe.py (mlx-whisper-large-v3-turbo
+ Voxtral-Mini-3B-2507-bf16 lazy-loaded + pyannote 3.1 on MPS, :8924),
mlx-speech.py (Kokoro 82M + Qwen3-TTS Custom/Design/Base on :8918).

V7 added 3 bench-only candidates:

- Voxtral-Mini-4B-Realtime-2602 (streaming ASR, ~570ms TTFT claim)
- Voxtral-4B-TTS-2603 (20 voices × 9 languages)
- Granite-Speech-4.1-2B (#1 OpenASR, keyword biasing)

A dedicated speech-shootout task should:

1. Build a probe driver exercising each model with the same audio corpus
   (multilingual, domain-vocab, streaming-vs-batched).
2. Score on WER, keyword F1, TTFT, and (for TTS) subjective Likert.
3. Produce a Pareto frontier for the speech lane equivalent to bench_tps.py
   for the text lane.
4. Promote winners to production replacement candidates only after the
   Pareto shows clear wins.

bench_tps.py is the wrong tool for this — its text-prompt harness does
not exercise streaming ASR or TTS rendering.

---
