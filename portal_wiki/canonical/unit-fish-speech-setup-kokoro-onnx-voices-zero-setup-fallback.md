---
id: unit-fish-speech-setup-kokoro-onnx-voices-zero-setup-fallback
kind: what
title: "FISH_SPEECH_SETUP \u2014 kokoro-onnx Voices (zero-setup fallback)"
sources:
- type: code
  path: portal/modules/media/tools/tts_mcp.py
- type: code
  path: .env.example
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.540277
updated_at: 1784946220.540277
---

The Kokoro voice set is defined twice in the repository, in the `list_voices`
tool of the TTS MCP and in the `.env.example` comment for `TTS_DEFAULT_VOICE`,
and the two agree:

| Voice ID | Accent / gender |
|----------|-----------------|
| `af_heart` | American English female (default) |
| `af_sky` | American English female |
| `af_bella` | American English female |
| `af_nicole` | American English female |
| `af_sarah` | American English female |
| `am_adam` | American English male |
| `am_michael` | American English male |
| `bf_emma` | British English female |
| `bf_isabella` | British English female |
| `bm_george` | British English male |
| `bm_lewis` | British English male |

`af_heart` is the fallback when no `voice` argument is supplied, because it is the
value of `TTS_DEFAULT_VOICE` and the server-side `TTS_VOICE` default.

## Why

A voice table is only safe to document when a tool actually returns it, and
`list_voices` returns exactly these eleven IDs, so the table is grounded in
executable output rather than marketing copy. Matching the `.env.example` comment
confirms the two sources of truth have not drifted apart from each other.
