---
id: unit-HOWTO-returns-status-ok-service-mlx-speech
historical: true
kind: why
title: "HOWTO \u2014 Returns: {\"status\": \"ok\", \"service\": \"mlx-speech\"}"
sources:
- type: design
  path: docs/HOWTO.md
  section: 'Returns: {"status": "ok", "service": "mlx-speech"}'
confidence: high
tags:
- docs
- HOWTO

---

```

**Note:** The first transcription downloads the Qwen3-ASR model (~800MB). Subsequent calls are instant.

**Fallback:** Docker `mcp-whisper` (:8915) and `mcp-tts` (:8916) still run as backup on non-Apple-Silicon hosts.

---
