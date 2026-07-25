---
id: unit-fish-speech-setup-alternative-kokoro-onnx-built-in-no-setup
kind: what
title: "FISH_SPEECH_SETUP \u2014 Alternative: kokoro-onnx (built-in, no setup)"
sources:
- type: doc
  path: docs/FISH_SPEECH_SETUP.md
  commit: 05e42ec2
  section: 'Alternative: kokoro-onnx (built-in, no setup)'
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.543301
updated_at: 1784946220.543301
---

If Fish Speech doesn't work on your system, set `TTS_BACKEND=kokoro` in `.env`.
kokoro-onnx is already installed inside the `mcp-tts` Docker container and requires
no additional setup. Its model (~60 MB) is downloaded automatically on first use.

kokoro-onnx provides:
- 11 English voices (American and British, male and female)
- Fast CPU inference via ONNX runtime
- No GPU required
