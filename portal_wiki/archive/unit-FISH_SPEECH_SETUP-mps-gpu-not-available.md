---
id: unit-FISH_SPEECH_SETUP-mps-gpu-not-available
kind: why
title: "FISH_SPEECH_SETUP \u2014 MPS/GPU not available"
sources:
- type: design
  path: docs/FISH_SPEECH_SETUP.md
  section: MPS/GPU not available
last_generated_commit: ''
confidence: high
tags:
- docs
- FISH_SPEECH_SETUP
created_at: 1783195000.837613
updated_at: 1783195000.837613
---

Fish Speech will fall back to CPU inference. This is slower but works:
```bash
python -m tools.api --device cpu --port 5005
```
