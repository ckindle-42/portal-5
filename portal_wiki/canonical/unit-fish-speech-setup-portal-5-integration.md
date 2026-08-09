---
id: unit-fish-speech-setup-portal-5-integration
kind: what
title: "Portal integration \u2014 TTS MCP tools and environment wiring"
sources:
- type: code
  path: config/portal.yaml
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: .env.example
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: scripts/mlx-speech.py
last_generated_commit: 925f52c4b7e7ec876ea24823d3a221c7f2f8f505
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5396202
updated_at: 1784946220.5396202
---

Integration with Portal 5 runs through the TTS MCP and the environment knobs that
configure it. `config/portal.yaml` registers the `tts` server as `portal-tts` on
port 8916, `docker-compose.yml` builds and runs it as the `mcp-tts` service
passing `TTS_BACKEND` and `TTS_DEFAULT_VOICE`, and `.env.example` documents those
variables. There is no `FISH_SPEECH_URL` variable anywhere in the repository; the
optional backend is chosen by setting `TTS_BACKEND=fish_speech`. Separately, Open
WebUI's own audio output does not use this MCP at all: the compose file points
`AUDIO_TTS_OPENAI_API_BASE_URL` at the host-native speech server on port 8918
(`scripts/mlx-speech.py`), which serves Kokoro and Qwen3-TTS.

## Why

The old guide invented an HTTP URL that the code never reads, and tracing the real
integration exposes two distinct speech surfaces that are easy to confuse: the
MCP tool server for persona tool-calls and the OpenAI-compatible server Open
WebUI speaks to directly. Naming both keeps operators from editing a variable
that does nothing while the actual switch lives in `TTS_BACKEND`.
