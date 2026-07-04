---
id: unit-FISH_SPEECH_SETUP-portal-5-integration
kind: why
title: "FISH_SPEECH_SETUP \u2014 Portal 5 Integration"
sources:
- type: design
  path: docs/FISH_SPEECH_SETUP.md
  section: Portal 5 Integration
last_generated_commit: ''
confidence: high
tags:
- docs
- FISH_SPEECH_SETUP
created_at: 1783195000.836216
updated_at: 1783195000.836216
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
