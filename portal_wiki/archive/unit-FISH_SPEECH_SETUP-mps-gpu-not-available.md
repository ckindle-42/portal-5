---
id: unit-FISH_SPEECH_SETUP-mps-gpu-not-available
historical: true
kind: why
title: "FISH_SPEECH_SETUP \u2014 MPS/GPU not available"
sources:
- type: design
  path: docs/FISH_SPEECH_SETUP.md
  section: MPS/GPU not available
confidence: high
tags:
- docs
- FISH_SPEECH_SETUP

---

Fish Speech will fall back to CPU inference. This is slower but works:
```bash
python -m tools.api --device cpu --port 5005
```
