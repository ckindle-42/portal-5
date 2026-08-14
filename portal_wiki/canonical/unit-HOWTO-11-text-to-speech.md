---
id: unit-HOWTO-11-text-to-speech
kind: why
title: "HOWTO \u2014 11. Text-to-Speech"
sources:
- type: code
  path: scripts/mlx-speech.py
- type: code
  path: scripts/lib/services.sh
- type: code
  path: config/portal.yaml
last_generated_commit: 64c5f5f41652bf67e97863ee1a6285289eaeea00
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.846459
updated_at: 1783195000.846459
---

**What:** Convert text to spoken audio using MLX-native speech (Kokoro + Qwen3-TTS).

**Activate:** Select `Music Producer` (`auto-music`) from the model dropdown. The TTS tools (`speak`, `clone_voice`, `list_voices`) are granted by `auto-music`'s `tools` list in `config/portal.yaml` — they are not available in every workspace.

**How:** The host-native MLX speech server (`scripts/mlx-speech.py`, port 8918) provides TTS via Kokoro (default backend, `af_heart` default voice) and Qwen3-TTS (voice cloning, emotion control, 10 languages). Start it with `./launch.sh start-speech` — `_launch_start_speech` in `scripts/lib/services.sh` requires Apple Silicon and `mlx-audio`, and models load lazily on the first request. The Docker `mcp-tts` container (port 8916, `portal/modules/media/tools/tts_mcp.py`) is the fallback tool server, defaulting to the kokoro-onnx backend. Audio files land in `generated/speech/` and the tool returns a download URL.

## Why

Speech is an audio runtime, not part of the chat inference tier, so it runs outside Ollama entirely: a native server on Apple Silicon uses the Metal GPU for fast synthesis while the MCP tool layer keeps the model-facing call uniform. Lazy model loading keeps `start-speech` cheap to bring up — the first utterance pays the load cost, not the startup command.
