---
id: unit-fish-speech-setup-test-tts-mcp-directly
kind: what
title: "FISH_SPEECH_SETUP \u2014 Test TTS MCP directly"
sources:
- type: doc
  path: docs/FISH_SPEECH_SETUP.md
  commit: 05e42ec2
  section: Test TTS MCP directly
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5419881
updated_at: 1784946220.5419881
---

curl -X POST http://localhost:8916/tools/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from Portal 5!", "voice": "english_alice"}'
```
