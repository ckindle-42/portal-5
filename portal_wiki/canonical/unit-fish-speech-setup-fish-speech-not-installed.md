---
id: unit-fish-speech-setup-fish-speech-not-installed
kind: what
title: "FISH_SPEECH_SETUP \u2014 Fish Speech not installed"
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: launch.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5422988
updated_at: 1784946220.5422988
---

When the optional `fish_speech` package is absent, the TTS MCP still serves
speech through Kokoro: `_get_available_backend` reports `kokoro` whenever the
`kokoro_onnx` import succeeds, and the `speak` tool falls back to the default
`TTS_BACKEND` value. To confirm which backend is live, `curl
http://localhost:8916/health` returns JSON with the `backend` field set to
`kokoro` or `fish_speech`, and `./launch.sh logs mcp-tts` shows the runtime log
of the service. That same health route is what `docker-compose.yml` polls for
the container healthcheck, so the probe is shared with the platform itself.

## Why

A speech system that silently degrades is only useful if the active backend is
observable, and the health route plus the compose healthcheck provide that
observability mechanically. This unit records the exact commands so an operator
diagnosing silence can tell a missing optional backend apart from a real
synthesis failure without guessing.
