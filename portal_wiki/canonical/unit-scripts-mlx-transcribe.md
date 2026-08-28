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
updated_at: 1787934168.0
---

Host-native transcription server for Apple Silicon. `transcribe_audio` is fast plain transcription via Parakeet-TDT-v3 (word-level timestamps). `transcribe_with_speakers` runs the same Parakeet transcript plus Sortformer speaker diarization (`mlx-community/diar_sortformer_4spk-v1-fp32`, 4-speaker ceiling), merged at the word level: each Parakeet word is assigned to the Sortformer speaker whose turn it overlaps, then consecutive same-speaker words are grouped into turns. A monologue collapses to one speaker; a conversation gets `SPEAKER_00`/`SPEAKER_01`/… No pyannote and no HuggingFace token. If diarization is skipped (file past `MLX_DIARIZE_MAX_S`) or fails, the transcript is still returned single-speaker with a `warning` — it never truncates.

## Why

Running transcription host-native on Metal is the performance answer on Apple Silicon. Splitting transcription (Parakeet) from diarization (Sortformer) rather than using one joint model means a diarization failure costs only the speaker labels, never the transcript — a joint model that stops early on a long monologue loses both. Word-level assignment keeps a speaker change on a word boundary; a short run wedged between two runs of the same other speaker is smoothed away as a boundary wobble. Sortformer's forward pass is ~0.5s for a few minutes of audio, so the diarized path is only marginally slower than plain transcription.

## Interfaces

The script is an operator or agent tool run from the repo root; it prints its findings and exits with the appropriate status.

## Gotchas

As a standalone script it reads live state — run it with the stack or environment it expects, and treat its output as current reality, not a stale record.
