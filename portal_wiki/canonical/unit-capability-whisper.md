---
id: unit-capability-whisper
kind: mixed
title: "Whisper MCP \u2014 transcription and diarization"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: portal/modules/media/tools/whisper_mcp.py
- type: code
  path: config/inference/tools_manifest_whisper_mcp.json
claims: []
confidence: high
tags:
- capability
- mcp
- media
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# Whisper MCP — transcription and diarization

## What

The Whisper MCP (`portal/modules/media/tools/whisper_mcp.py`, port 8915)
transcribes audio to text. It is pipeline- and IDE-exposed and backs the
`auto-audio` workspace, serving the transcription lane alongside the separate
MLX transcribe server.

## How it's used

`transcribe_audio` converts an audio file to a timestamped transcript;
`transcribe_with_speakers` adds speaker turns via diarization and writes both a
JSON and a Markdown transcript into the shared generated transcripts directory.
An audio reference resolves from an OWUI file id, a filename in the uploads
directory, or an absolute host path, and a missing reference auto-detects the
most recent upload.

## Why it exists

Transcription is a distinct capability from speech synthesis — it consumes
uploaded audio and produces structured text, with diarization as the premium
path. Exposing it through the whisper MCP keeps the media module's audio
surface coherent: one server for speech-to-text, one for text-to-speech, each
with its own dependencies and latency profile.

## Value

Meetings and voice notes become searchable, timestamped, speaker-labeled text
with a single tool call, and the Markdown output is display-ready in the chat.
The flexible audio-reference resolution is what makes it usable from a chat
attachment, a filename, or a host path interchangeably.
