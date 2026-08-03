---
id: unit-scripts-mlx-transcribe
kind: mixed
title: "Script \u2014 mlx-transcribe"
sources:
- type: code
  path: scripts/mlx-transcribe.py
  commit: af437ebd
last_generated_commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799539.676291
updated_at: 1785799539.676291
---

Host-native diarized transcription server for Apple Silicon: mlx-whisper for transcription and pyannote.audio on MPS for diarization.

## Why

Diarized transcription needs speaker separation, and running it host-native on Metal is the performance answer on Apple Silicon. The server pairs the Metal-accelerated whisper transcription with the MPS diarization so the fleet has a single transcription surface.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
