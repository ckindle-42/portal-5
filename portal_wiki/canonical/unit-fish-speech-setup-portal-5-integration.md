---
id: unit-fish-speech-setup-portal-5-integration
kind: what
title: "FISH_SPEECH_SETUP \u2014 Portal 5 Integration"
sources:
- type: doc
  path: docs/FISH_SPEECH_SETUP.md
  commit: 05e42ec2
  section: Portal 5 Integration
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5396202
updated_at: 1784946220.5396202
---

The TTS MCP expects Fish Speech API at `http://localhost:5005` by default.

Set environment variable in `.env`:
```
FISH_SPEECH_URL=http://localhost:5005
```

To switch back to the built-in kokoro-onnx backend, set in `.env`:
```
TTS_BACKEND=kokoro
```
