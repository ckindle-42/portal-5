---
id: unit-FISH_SPEECH_SETUP-portal-6-0-0-fish-speech-setup-guide
kind: why
title: "FISH_SPEECH_SETUP \u2014 Portal 6.0.0 \u2014 Fish Speech Setup Guide"
sources:
- type: design
  path: docs/FISH_SPEECH_SETUP.md
  section: "Portal 6.0.0 \u2014 Fish Speech Setup Guide"
last_generated_commit: ''
confidence: high
tags:
- docs
- FISH_SPEECH_SETUP
created_at: 1783195000.834454
updated_at: 1783195000.834454
---


Fish Speech is an **optional** TTS backend for Portal 5 that adds high-quality voice
cloning. It runs outside Docker on the host machine to access GPU/MPS hardware directly.

**Default (zero-setup)**: Portal 5 ships with **kokoro-onnx** as the primary TTS backend.
It downloads its model (~60 MB) automatically on first use — no setup required.
Fish Speech is only needed if you want voice cloning from reference audio.

**Note**: If Fish Speech is not configured, the TTS MCP automatically uses kokoro-onnx.
