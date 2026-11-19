---
id: unit-HOWTO-direct-api-call
historical: true
kind: why
title: "HOWTO \u2014 Direct API call"
sources:
- type: design
  path: docs/HOWTO.md
  section: Direct API call
confidence: high
tags:
- docs
- HOWTO

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
