---
id: unit-FISH_SPEECH_SETUP-voice-cloning
kind: why
title: "FISH_SPEECH_SETUP \u2014 Voice Cloning"
sources:
- type: design
  path: docs/FISH_SPEECH_SETUP.md
  section: Voice Cloning
last_generated_commit: ''
confidence: high
tags:
- docs
- FISH_SPEECH_SETUP
created_at: 1783195000.8369112
updated_at: 1783195000.8369112
---


Fish Speech supports zero-shot voice cloning from reference audio:

1. Prepare reference audio (5-30 seconds, clean speech)
2. Use the `clone_voice` tool in Open WebUI
3. Provide path to reference audio and text to synthesize
