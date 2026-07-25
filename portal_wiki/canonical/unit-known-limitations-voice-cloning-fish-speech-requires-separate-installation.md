---
id: unit-known-limitations-voice-cloning-fish-speech-requires-separate-installation
kind: what
title: "KNOWN_LIMITATIONS \u2014 Voice Cloning (fish-speech) Requires Separate Installation"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: Voice Cloning (fish-speech) Requires Separate Installation
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.6634922
updated_at: 1784946220.6634922
---

- **Description**: Voice cloning via `fish-speech` is not in the Docker stack — requires host-side installation. The docker `tts_mcp` `clone_voice` tool requires it and errors without it.
- **Impact**: The docker-side `clone_voice` tool is unavailable without fish-speech installed.
- **Mitigation**: Voice cloning still works without fish-speech via the native `mlx-speech` service (`:8918`, `POST /v1/audio/speech` with `voice: "clone:/path/to/reference.wav"`, Qwen3-TTS Base-Clone) — verified during Slice P media bring-up (`TASK_MEDIA_BRINGUP_V1`). `kokoro-onnx` covers non-cloned TTS out of the box either way. See `docs/FISH_SPEECH_SETUP.md` for fish-speech.
