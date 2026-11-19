---
id: unit-FISH_SPEECH_SETUP-start-api-server-on-port-5005
historical: true
kind: why
title: "FISH_SPEECH_SETUP \u2014 Start API server on port 5005"
sources:
- type: design
  path: docs/FISH_SPEECH_SETUP.md
  section: Start API server on port 5005
confidence: high
tags:
- docs
- FISH_SPEECH_SETUP

---

python -m tools.api --device mps --port 5005
```

**Note**: For CPU-only inference, use `--device cpu` instead of `--device mps`.
