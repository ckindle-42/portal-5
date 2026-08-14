---
id: unit-known-limitations-owui-audio-drop-ux-task-owui-audio-drop-001
kind: what
title: "KNOWN_LIMITATIONS \u2014 OWUI Audio Drop UX (TASK-OWUI-AUDIO-DROP-001)"
sources:
- type: code
  path: .env.example
- type: code
  path: scripts/transcribe_and_complete.sh
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.675196
updated_at: 1784946220.675196
---

- **OWUI internal tool-call ceiling.** Some OWUI builds enforce a hard internal timeout on tool execution that `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` does not affect; `.env.example` sets that variable to 1800 but the OWUI-side ceiling can still fire. When it does, the tool completes server-side but the persona never sees the result. Use `scripts/transcribe_and_complete.sh` for files whose wall time exceeds the ceiling.
- **WEBUI_SECRET_KEY rotation invalidates OAuth tokens.** If `.env` is regenerated and the secret key changes, all MCP OAuth tools need re-authentication. The variable is set in `.env.example` with a placeholder.
- **Microphone voice input remains disabled.** `.env.example` leaves `OWUI_AUDIO_STT_ENGINE` empty, disabling auto-transcription of audio uploads and microphone recordings; this trade-off keeps audio accessible to the personas.

## Why

The tool server timeout is only one knob in a two-sided timeout path: `.env.example` raises Portal's client timeout, but an OWUI-side hard ceiling can still drop a completed result, so the surviving workaround is a script that completes transcription out of band. Recording the three audio-UX constraints together keeps the known failure modes and their environment variables in one place for an operator diagnosing a dropped file.
