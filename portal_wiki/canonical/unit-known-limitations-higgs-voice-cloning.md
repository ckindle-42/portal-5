---
id: unit-known-limitations-higgs-voice-cloning
kind: mixed
title: "Known Limitation — Voice Cloning (Higgs Audio v2)"
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
updated_at: 1787924000
---

### Voice Cloning Constraints

- **ID**: P5-SPEECH-CLONE-001
- **Description**: Cloning runs through `mlx-community/higgs-audio-v2-3B-mlx-q8` (Boson AI
  Higgs Audio v2) in the host `scripts/mlx-speech.py` — Apple-Silicon-only, no
  CPU/CUDA/Docker path (the Docker `tts_mcp.py` only proxies to it). It is zero-shot from
  a clip/profile — **not** a fine-tune, so fidelity tracks reference-clip quality, and the
  engine reads only the first ~10-15s of the reference (a tight, expressive clip beats a
  long flat one). Output is 24 kHz. Higgs Audio v2 emits **no provenance watermark**, so
  clones cannot be automatically identified as AI-generated. The engine was chosen over
  Chatterbox (`mlx-community/chatterbox-fp16`, still selectable via `MLX_CLONE_MODEL`) in
  the operator fidelity gate — Chatterbox's 24 kHz output was consistently ~1 kHz darker in
  spectral centroid than the reference; Higgs tracked it closely. Higgs is a 3B model:
  measured on this host, load ~3s (warm; first pull ~3-4 GB of weights), per-clone ~4s,
  ~7 GB peak working set (vs Chatterbox ~3.4 GB).
- **Impact**: Off Apple Silicon, cloning is unavailable. A poor reference yields a poor
  clone. Unwatermarked output should not be presented as an indistinguishable real
  recording.
- **Mitigation**: Capture trainer reference clips carefully (quiet room, close mic,
  10-15s, natural conversational delivery, accurate transcript) and register them as
  profiles once — via the `register_voice` tool, `POST /v1/voices`, or
  `scripts/register_trainer_voice.py`. Set `MLX_CLONE_MODEL=mlx-community/chatterbox-fp16`
  to fall back to the lighter engine.

## Why

A register-once/reuse profile design fits the training use case better than per-call
cloning, and storing the reference WAV+transcript (not a serialized embedding) keeps
profiles valid across mlx-audio upgrades and across an engine swap. Recording the engine
choice, the no-watermark fact, and the no-fallback constraint here keeps them visible in
the limitations register.
