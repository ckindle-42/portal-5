---
id: unit-FISH_SPEECH_SETUP-voice-cloning
historical: true
kind: why
title: "FISH_SPEECH_SETUP \u2014 Voice Cloning"
sources:
- type: design
  path: docs/FISH_SPEECH_SETUP.md
  section: Voice Cloning
confidence: high
tags:
- docs
- FISH_SPEECH_SETUP

---


Fish Speech supports zero-shot voice cloning from reference audio:

1. Prepare reference audio (5-30 seconds, clean speech)
2. Use the `clone_voice` tool in Open WebUI
3. Provide path to reference audio and text to synthesize
