---
id: unit-fish-speech-setup-test-tts-mcp-directly
kind: what
title: Test the TTS MCP speak tool directly
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: deploy/portal-5/docker-compose.yml
last_generated_commit: f28832a459fb834ed6696f953f9955694b962483
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.5419881
updated_at: 1784946220.5419881
---

The `speak` tool is reachable over HTTP at the MCP's `/tools/speak` route, which
expects an `arguments` wrapper, so a direct request must wrap the tool arguments:

```bash
curl -X POST http://localhost:8916/tools/speak \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"text": "Hello from Portal 5!", "voice": "af_heart"}}'
```

The handler reads the `arguments` field and forwards `text`, `voice`, `speed` and
`backend` into the `speak` function, returning JSON with a `download_url` to the
generated WAV when synthesis succeeds. The voice name english_alice from the old
guide is not something the server knows; the valid preset IDs are the Kokoro list
in `list_voices` plus the Fish Speech IDs `female_zhang` and `male_yun`.

## Why

The old example posted a bare tool payload and a voice name that no code defines,
so it would fail even against a healthy server. The corrected shape mirrors what
the route actually parses, and using a real voice ID makes the test distinguish a
working stack from a voice-routing problem.
