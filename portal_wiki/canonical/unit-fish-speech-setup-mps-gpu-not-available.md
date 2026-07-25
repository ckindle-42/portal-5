---
id: unit-fish-speech-setup-mps-gpu-not-available
kind: what
title: "FISH_SPEECH_SETUP \u2014 MPS/GPU not available"
sources:
- type: doc
  path: docs/FISH_SPEECH_SETUP.md
  commit: 05e42ec2
  section: MPS/GPU not available
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.54262
updated_at: 1784946220.54262
---

Fish Speech will fall back to CPU inference. This is slower but works:
```bash
python -m tools.api --device cpu --port 5005
```
