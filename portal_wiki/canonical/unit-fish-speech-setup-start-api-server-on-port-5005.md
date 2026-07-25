---
id: unit-fish-speech-setup-start-api-server-on-port-5005
kind: what
title: "FISH_SPEECH_SETUP \u2014 Start API server on port 5005"
sources:
- type: doc
  path: docs/FISH_SPEECH_SETUP.md
  commit: 05e42ec2
  section: Start API server on port 5005
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.539288
updated_at: 1784946220.539288
---

python -m tools.api --device mps --port 5005
```

**Note**: For CPU-only inference, use `--device cpu` instead of `--device mps`.
