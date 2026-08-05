---
id: unit-fish-speech-setup-alternative-kokoro-onnx-built-in-no-setup
kind: what
title: "FISH_SPEECH_SETUP \u2014 Alternative: kokoro-onnx (built-in, no setup)"
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: Dockerfile.mcp
- type: code
  path: .env.example
- type: code
  path: scripts/mlx-speech.py
last_generated_commit: 3d2aca98eaf073d6bc9028a05b44d5321f3f2d87
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.543301
updated_at: 1784946220.543301
---

Setting `TTS_BACKEND=kokoro` in the environment selects the built-in backend, and
`.env.example` already ships that value as the default while `docker-compose.yml`
passes it to the `mcp-tts` container. `Dockerfile.mcp` installs `kokoro-onnx` at
image build time, so the container needs no per-run setup. On the first `speak`
call, `_ensure_kokoro_models` downloads the ONNX weights and the voices binary
from the upstream GitHub release and caches them under `HF_HOME`. The `list_voices`
tool reports eleven English voices spanning American and British male and female
speakers, and synthesis runs on CPU through the ONNX runtime, so no GPU and no
Hugging Face token are required. The host-native `mlx-speech` server is a second
Kokoro path that selects the same backend through `MLX_TTS_BACKEND` for Open
WebUI audio output.

## Why

Kokoro is the deliberate default because it collapses speech into one pip
dependency plus an on-demand model download, preserving the zero-setup contract
the container image promises. Fish Speech stays optional precisely because it
adds a heavy package and a large checkpoint, and it exists only to unlock voice
cloning from a reference recording, which the built-in backend cannot do.
