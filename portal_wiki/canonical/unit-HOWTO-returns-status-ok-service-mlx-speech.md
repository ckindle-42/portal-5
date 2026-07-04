---
id: unit-HOWTO-returns-status-ok-service-mlx-speech
kind: why
title: "HOWTO \u2014 Returns: {\"status\": \"ok\", \"service\": \"mlx-speech\"}"
sources:
- type: design
  path: docs/HOWTO.md
  section: 'Returns: {"status": "ok", "service": "mlx-speech"}'
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.848414
updated_at: 1783195000.848414
---

```

**Note:** The first transcription downloads the Qwen3-ASR model (~800MB). Subsequent calls are instant.

**Fallback:** Docker `mcp-whisper` (:8915) and `mcp-tts` (:8916) still run as backup on non-Apple-Silicon hosts.

---
