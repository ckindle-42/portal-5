---
id: unit-FISH_SPEECH_SETUP-fish-speech-not-installed
kind: why
title: "FISH_SPEECH_SETUP \u2014 Fish Speech not installed"
sources:
- type: design
  path: docs/FISH_SPEECH_SETUP.md
  section: Fish Speech not installed
last_generated_commit: ''
confidence: high
tags:
- docs
- FISH_SPEECH_SETUP
created_at: 1783195000.837373
updated_at: 1783195000.837373
---

The TTS MCP automatically uses kokoro-onnx when Fish Speech is not configured.
To confirm which backend is active:
```bash
curl http://localhost:8916/health   # returns {"backend": "kokoro"} or {"backend": "fish_speech"}
./launch.sh logs mcp-tts
```
