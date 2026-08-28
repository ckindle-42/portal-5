---
id: unit-known-limitations-diarized-transcription-task-transcribe-001
kind: what
title: "KNOWN_LIMITATIONS \u2014 Diarized Transcription (TASK-TRANSCRIBE-001)"
sources:
- type: code
  path: scripts/mlx-transcribe.py
- type: code
  path: portal/modules/media/tools/whisper_mcp.py
- type: code
  path: .env.example
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.674855
updated_at: 1787879900.0
---

- **VibeVoice-ASR is a 9B model — materially slower than whisper-turbo.** `scripts/mlx-transcribe.py` runs diarized transcription through `mlx-community/VibeVoice-ASR-bf16`. Give long files generous wall-clock headroom (Phase 2 smoke: first model load ~25s, then ~30s to transcribe an 18-second 2-speaker clip). Long-form support is ~60 min.
- **Apple-Silicon-only for the primary path.** The Docker fallback (`portal/modules/media/tools/whisper_mcp.py`) is faster-whisper `large-v3-turbo` with **no diarization** — speaker identification requires the host MLX server (:8924), and `transcribe_with_speakers` returns an error when that host is unreachable.
- **Speakers are model-inferred, not named.** Labels are `SPEAKER_00`, `SPEAKER_01`, … A `num_speakers` hint is accepted for API compatibility but VibeVoice infers speaker count itself.
- **OWUI tool-call timeout for long files.** OWUI's MCP tool-call ceiling can fire before a long file finishes. Raise `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` (set to 1800 in `.env.example`) or use the direct endpoint on port `8924`.

## Why

Single-pass diarized transcription (one model emits text + speaker + timestamps) removes the entire class of alignment bugs the previous mlx-whisper + pyannote greedy-overlap merge had (overlap collapse, speaker-count drift) and drops the `HF_TOKEN` gate, at the cost of a slower 9B forward pass. Sortformer + Parakeet remains the documented future two-stage upgrade if its mlx-audio Python API is confirmed.
