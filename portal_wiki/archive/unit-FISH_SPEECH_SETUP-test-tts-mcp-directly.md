---
id: unit-FISH_SPEECH_SETUP-test-tts-mcp-directly
historical: true
kind: why
title: "FISH_SPEECH_SETUP \u2014 Test TTS MCP directly"
sources:
- type: design
  path: docs/FISH_SPEECH_SETUP.md
  section: Test TTS MCP directly
confidence: high
tags:
- docs
- FISH_SPEECH_SETUP

---

curl -X POST http://localhost:8916/tools/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from Portal 5!", "voice": "english_alice"}'
```
