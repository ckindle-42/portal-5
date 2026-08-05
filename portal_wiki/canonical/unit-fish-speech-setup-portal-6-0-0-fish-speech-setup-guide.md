---
id: unit-fish-speech-setup-portal-6-0-0-fish-speech-setup-guide
kind: what
title: "Portal 5 Fish Speech setup \u2014 overview"
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: Dockerfile.mcp
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.536432
updated_at: 1784946220.536432
---

Fish Speech is an optional TTS backend for Portal 5 whose only unique feature is
voice cloning from a reference recording, and it is not the default. The default
is Kokoro: `TTS_BACKEND` defaults to `kokoro`, `Dockerfile.mcp` installs
`kokoro-onnx` in the `mcp-tts` container, and `_ensure_kokoro_models` fetches the
ONNX weights and voices on first use with no operator action. When the optional
`fish_speech` package is missing, `_get_available_backend` and the `speak` tool
keep serving through Kokoro, so the system degrades to the built-in backend
rather than failing. Fish Speech does not run outside Docker; the MCP imports it
in-process and the service answers on port 8916.

## Why

This is the umbrella unit for the setup guide, so its job is to state the
default-versus-optional relationship once and accurately. Getting the container
boundary right matters here more than anywhere else because the old doc claimed
Fish Speech runs on the host for MPS, when the current code loads it inside the
mcp-tts process and leaves host MPS to the separate speech server.
