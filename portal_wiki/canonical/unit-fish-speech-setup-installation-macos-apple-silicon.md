---
id: unit-fish-speech-setup-installation-macos-apple-silicon
kind: what
title: Installation on macOS Apple Silicon
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/mlx-speech.py
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: Dockerfile.mcp
- type: code
  path: portal/modules/media/tools/tts_mcp.py
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.536941
updated_at: 1784946220.536941
---

On macOS Apple Silicon there is no Portal-specific Fish Speech installer;
`launch.sh` manages `install-comfyui`, `install-music-minimax`,
`install-music-ace`, and the host-native speech server, but nothing in the repo
provisions Fish Speech. The zero-setup
speech backend is Kokoro inside the `mcp-tts` container, which `Dockerfile.mcp`
supplies at build time, while the host speech server in `scripts/mlx-speech.py`
runs natively for MPS access and serves Open WebUI through
`AUDIO_TTS_OPENAI_API_BASE_URL` pointing at port 8918. Fish Speech remains a
manual, optional install whose checkpoint the TTS MCP loads from
`models/fish_speech/fish-speech-1.4`.

## Why

The original section was a code fence with nothing behind it, so the truthful
content is negative: this repository installs Kokoro, not Fish Speech, and macOS
users get MPS acceleration through the host-native speech server rather than
through the optional backend. Recording that boundary prevents an operator from
expecting a fish install command that does not exist in the codebase.
