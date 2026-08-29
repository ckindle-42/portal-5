---
id: unit-capability-mlx-transcribe
kind: mixed
title: "MLX Transcribe MCP \u2014 host-native diarized transcription"
sources:
- type: code
  path: config/portal.yaml
  section: mcp_fleet
- type: code
  path: scripts/mlx-transcribe.py
- type: code
  path: scripts/native-mcp-service.sh
claims: []
confidence: high
tags:
- capability
- mcp
- platform
created_at: 1788030600.446044
updated_at: 1788030600.446044
---

# MLX Transcribe MCP — host-native diarized transcription

## What

The MLX Transcribe MCP (port 8924) is a host-native service (`mlx-transcribe`
launchd label) served by `scripts/mlx-transcribe.py` under
`scripts/native-mcp-service.sh`. It runs Parakeet-TDT-v3 for transcription and
Sortformer for speaker diarization, merged at the word level. It is
pipeline- and IDE-exposed and is Apple-Silicon-only.

## How it's used

`transcribe_audio` returns a fast transcript with word-level timestamps;
`transcribe_with_speakers` adds speaker turns (up to four, `SPEAKER_00` ...) and
writes JSON plus a speaker-labeled Markdown file to the generated transcripts
directory, including download URLs. A monologue resolves to one speaker; a
diarization failure returns the full transcript under a single speaker with a
warning rather than truncating.

## Why it exists

Diarized transcription is the MLX-on-Metal lane for meetings and multi-speaker
audio, distinct from the container whisper MCP. Being host-native puts the
heavy MLX models on the accelerator that runs them, and running under launchd
keeps the service warm. HF-hub offline mode under launchd avoids the cached-file
revalidation hangs, and ffmpeg is made findable for decoding phone-produced
uploads.

## Value

Conversations come back speaker-labeled and timestamped, ready to display or
search, with the audio reference resolving from an OWUI file id, an uploads
filename, or an absolute path. The word-level merge makes a long meeting
navigable and the Markdown output is immediately presentable in chat.
