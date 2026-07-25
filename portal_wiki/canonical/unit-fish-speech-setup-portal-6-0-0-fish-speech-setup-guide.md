---
id: unit-fish-speech-setup-portal-6-0-0-fish-speech-setup-guide
kind: what
title: "FISH_SPEECH_SETUP \u2014 Portal 6.0.0 \u2014 Fish Speech Setup Guide"
sources:
- type: doc
  path: docs/FISH_SPEECH_SETUP.md
  commit: 05e42ec2
  section: "Portal 6.0.0 \u2014 Fish Speech Setup Guide"
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.536432
updated_at: 1784946220.536432
---

Fish Speech is an **optional** TTS backend for Portal 5 that adds high-quality voice
cloning. It runs outside Docker on the host machine to access GPU/MPS hardware directly.

**Default (zero-setup)**: Portal 5 ships with **kokoro-onnx** as the primary TTS backend.
It downloads its model (~60 MB) automatically on first use — no setup required.
Fish Speech is only needed if you want voice cloning from reference audio.

**Note**: If Fish Speech is not configured, the TTS MCP automatically uses kokoro-onnx.
