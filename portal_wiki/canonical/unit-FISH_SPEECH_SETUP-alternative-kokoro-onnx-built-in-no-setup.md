---
id: unit-FISH_SPEECH_SETUP-alternative-kokoro-onnx-built-in-no-setup
kind: why
title: "FISH_SPEECH_SETUP \u2014 Alternative: kokoro-onnx (built-in, no setup)"
sources:
- type: design
  path: docs/FISH_SPEECH_SETUP.md
  section: 'Alternative: kokoro-onnx (built-in, no setup)'
last_generated_commit: ''
confidence: high
tags:
- docs
- FISH_SPEECH_SETUP
created_at: 1783195000.83807
updated_at: 1783195000.83807
---


If Fish Speech doesn't work on your system, set `TTS_BACKEND=kokoro` in `.env`.
kokoro-onnx is already installed inside the `mcp-tts` Docker container and requires
no additional setup. Its model (~60 MB) is downloaded automatically on first use.

kokoro-onnx provides:
- 11 English voices (American and British, male and female)
- Fast CPU inference via ONNX runtime
- No GPU required
