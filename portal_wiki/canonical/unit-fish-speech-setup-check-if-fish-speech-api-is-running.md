---
id: unit-fish-speech-setup-check-if-fish-speech-api-is-running
kind: what
title: "Checking the TTS backend \u2014 health route, not a Fish Speech API"
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: launch.sh
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.541662
updated_at: 1784946220.541662
---

There is no standalone Fish Speech API server in Portal 5; when the optional
`fish_speech` package is importable, the TTS MCP loads it in-process instead of
proxying to a separate process. The correct way to ask whether speech is ready is
the MCP's own health route: `curl http://localhost:8916/health` returns JSON
whose `backend` field reads either `kokoro` or `fish_speech`. `docker-compose.yml`
uses that same request as the container healthcheck, and `./launch.sh logs mcp-tts`
streams the service log for diagnosing failures at request time.

## Why

The older guide pointed operators at a port 5005 API that no code in this
repository runs, so that check could never succeed against a healthy stack.
Pinning the probe to the route the MCP actually serves makes the verification
meaningful and keeps it identical to the healthcheck Docker already executes for
the container.
