---
id: unit-fish-speech-setup-running-fish-speech
kind: what
title: "Running Fish Speech \u2014 via the mcp-tts container"
sources:
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: launch.sh
- type: code
  path: portal/modules/media/tools/tts_mcp.py
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.538971
updated_at: 1784946220.538971
---

There is no separate start command for Fish Speech because it is not a standalone
process. The `mcp-tts` service defined in `docker-compose.yml` runs the TTS MCP
module as its entrypoint, and the MCP imports the optional `fish_speech` package
in-process when `TTS_BACKEND=fish_speech`. Bringing the stack up with `launch.sh`
starts the service, and `./launch.sh logs mcp-tts` tails its output. The only
prerequisite for the backend to activate is that the `fish_speech` package is
importable and the 1.4 checkpoint sits at `models/fish_speech/fish-speech-1.4`,
which is the path `load_from_checkpoint` asserts.

## Why

Operators coming from the old guide expected to launch an upstream API process
before using TTS, but the container entrypoint already owns the whole lifecycle.
Grounding the run step in the compose command removes a spurious manual step and
makes it explicit that activation depends on the package and checkpoint being
present at the paths the loader code asserts.
