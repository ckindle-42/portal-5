---
id: unit-HOWTO-direct-api-call
kind: why
title: "HOWTO \u2014 Direct API call"
sources:
- type: design
  path: docs/HOWTO.md
  section: Direct API call
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.847775
updated_at: 1783195000.847775
---


```bash
curl -X POST http://localhost:8918/v1/audio/transcriptions \
  -F "file=@recording.mp3" \
  -F "language=English"
```

**Supported formats:** MP3, WAV, M4A, FLAC, OGG, WebM

**Verify:**
```bash
curl -s http://localhost:8918/health
