---
id: unit-scripts-mlx-transcribe
kind: mixed
title: "Script \u2014 mlx-transcribe"
sources:
- type: code
  path: scripts/mlx-transcribe.py
  commit: af437ebd
claims: []
confidence: high
tags:
- authored-v1
- scripts
created_at: 1785799539.676291
updated_at: 1787879900.0
---

Host-native transcription server for Apple Silicon. Fast transcription via Parakeet-TDT-v3 (word-level timestamps, transcribe_audio) and single-pass diarized transcription via VibeVoice-ASR (text + speaker labels + timestamps in one model, transcribe_with_speakers). No pyannote and no HuggingFace token — VibeVoice does diarization itself.

## Why

Running transcription host-native on Metal is the performance answer on Apple Silicon. A single model (VibeVoice-ASR) emitting text + speaker + timestamps in one pass removes the alignment-bug class of the previous mlx-whisper + pyannote greedy-overlap merge and drops the HF_TOKEN gate; Parakeet-TDT-v3 covers the fast path when speaker labels aren't needed.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
