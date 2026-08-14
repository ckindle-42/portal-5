---
id: unit-known-limitations-voice-cloning-fish-speech-requires-separate-installation
kind: what
title: "KNOWN_LIMITATIONS \u2014 Voice Cloning (fish-speech) Requires Separate Installation"
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: scripts/mlx-speech.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.6634922
updated_at: 1784946220.6634922
---

- **Description**: Voice cloning via `fish-speech` is not in the Docker stack — it requires host-side installation. The Docker `tts_mcp`'s `clone_voice` tool requires it: `_check_fish_speech` in `portal/modules/media/tools/tts_mcp.py` imports `fish_speech` and reports "fish-speech not installed (voice cloning unavailable)" on `ImportError`, and the `fish_speech` backend is selected only when that check passes.
- **Impact**: The docker-side `clone_voice` tool is unavailable without fish-speech installed.
- **Mitigation**: Voice cloning still works without fish-speech via the native `mlx-speech` service on port 8918: `scripts/mlx-speech.py` accepts `voice="clone:/path/to/reference.wav"` (Qwen3-TTS Base voice cloning from reference audio). `kokoro-onnx` covers non-cloned TTS out of the box either way, as `tts_mcp.py`'s backend fallback shows. See `docs/FISH_SPEECH_SETUP.md` for fish-speech.

## Why

fish-speech is a heavy optional dependency, so the container keeps it out and the MCP fails with a precise diagnostic rather than a vague error. The native `mlx-speech` service provides the same capability through a different mechanism, which keeps voice cloning available on the default stack while letting operators who want the higher-quality fish-speech path install it separately — two routes, one documented prerequisite each.
