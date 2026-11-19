---
id: unit-known-limitations-owui-audio-drop-ux-task-owui-audio-drop-001
kind: what
title: "KNOWN_LIMITATIONS — OWUI Audio Drop UX (TASK-OWUI-AUDIO-DROP-001)"
sources:
- type: code
  path: .env.example
- type: code
  path: scripts/mlx-transcribe.py
claims: []
confidence: high
tags:
- docs
- verified-v1

---

- **OWUI internal tool-call ceiling.** Some OWUI builds enforce a hard internal timeout on tool execution that `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` does not affect; `.env.example` sets that variable to 1800 but the OWUI-side ceiling can still fire. When it does, the model never sees the tool result — but the transcribe server has already written the JSON + Markdown + Word (`.docx`) sidecars to `~/AI_Output/generated/transcripts/`, so the transcript is not lost. For a file long enough to hit the ceiling, POST it straight to `http://localhost:8924/v1/audio/transcribe-with-speakers`.
- **WEBUI_SECRET_KEY rotation invalidates OAuth tokens.** If `.env` is regenerated and the secret key changes, all MCP OAuth tools need re-authentication. The variable is set in `.env.example` with a placeholder.
- **Microphone voice input depends on the ASR weights being fetched.** `.env.example` now sets `OWUI_AUDIO_STT_ENGINE=openai` so OWUI's mic and upload transcription go to the MLX transcribe server (:8924) instead of the in-container CPU faster-whisper "base". Both host audio services run with `HF_HUB_OFFLINE=1`, so `./launch.sh pull-asr-models` must run once (idempotent) before either can serve; until it has, `/health` reports `asr_available: false` and OWUI's STT call gets a `503` naming that command. OWUI itself keeps working — chat, uploads and the MCP transcription tools are unaffected.

## Why

The tool server timeout is only one knob in a two-sided timeout path: `.env.example` raises Portal's client timeout, but an OWUI-side hard ceiling can still drop a completed result. Rather than work around it with an out-of-band script, the transcribe server writes all three sidecars (JSON, Markdown, `.docx`) before it replies, so a dropped chat turn costs the conversational summary, never the transcript. Recording the three audio-UX constraints together keeps the known failure modes and their environment variables in one place for an operator diagnosing a dropped file.
