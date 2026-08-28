---
id: unit-known-limitations-chatterbox-voice-cloning
kind: mixed
title: "Known Limitation — Chatterbox Voice Cloning"
sources:
- type: code
  path: scripts/mlx-speech.py
claims: []
confidence: high
tags:
- known-limitations
- speech
- apple-silicon
created_at: 1787921700
updated_at: 1787921700
---

### Chatterbox Voice Cloning Constraints

- **ID**: P5-SPEECH-CLONE-001
- **Description**: Cloning runs through `mlx-community/chatterbox-fp16` (English v2, MIT) in the
  host `scripts/mlx-speech.py` — Apple-Silicon-only, no CPU/CUDA/Docker path (the Docker
  `tts_mcp.py` only proxies to it). Every generated clip carries Resemble AI's **PerTh
  watermark** — an inaudible, traceable provenance marker; it does not restrict use but marks
  output as AI-generated. Cloning is zero-shot from a clip/profile — **not** a fine-tune, so
  fidelity tracks reference-clip quality (10-15s clean close-mic clones best). English v2.
  Measured on this host: model load ~3s (warm; first pull downloads ~2GB of weights),
  per-clone ~3s for a short sentence, ~3.4GB peak working set.
- **Impact**: Off Apple Silicon, cloning is unavailable. Watermarked output should not be
  presented as an indistinguishable real recording. A poor reference yields a poor clone.
- **Mitigation**: Capture trainer reference clips carefully (quiet room, close mic, 10-15s,
  accurate transcript) and register them as profiles once. None else needed for this
  single-user deployment.

## Why

A register-once/reuse profile design fits the training use case better than per-call cloning, and
storing the reference WAV+transcript (not a serialized embedding) keeps profiles valid across
mlx-audio upgrades. Recording the PerTh watermark and no-fallback constraint here keeps them
visible in the limitations register.
