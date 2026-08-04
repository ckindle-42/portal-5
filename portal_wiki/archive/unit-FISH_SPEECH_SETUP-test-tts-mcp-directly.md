---
id: unit-FISH_SPEECH_SETUP-test-tts-mcp-directly
kind: why
title: "FISH_SPEECH_SETUP \u2014 Test TTS MCP directly"
sources:
- type: design
  path: docs/FISH_SPEECH_SETUP.md
  section: Test TTS MCP directly
last_generated_commit: ''
confidence: high
tags:
- docs
- FISH_SPEECH_SETUP
created_at: 1783195000.837139
updated_at: 1783195000.837139
---

curl -X POST http://localhost:8916/tools/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from Portal 5!", "voice": "english_alice"}'
```
