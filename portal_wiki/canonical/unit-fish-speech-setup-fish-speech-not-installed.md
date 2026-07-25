---
id: unit-fish-speech-setup-fish-speech-not-installed
kind: what
title: "FISH_SPEECH_SETUP \u2014 Fish Speech not installed"
sources:
- type: doc
  path: docs/FISH_SPEECH_SETUP.md
  commit: 05e42ec2
  section: Fish Speech not installed
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5422988
updated_at: 1784946220.5422988
---

The TTS MCP automatically uses kokoro-onnx when Fish Speech is not configured.
To confirm which backend is active:
```bash
curl http://localhost:8916/health   # returns {"backend": "kokoro"} or {"backend": "fish_speech"}
./launch.sh logs mcp-tts
```
