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
updated_at: 1787927539.0
---

- **VibeVoice-ASR is a 9B model — materially slower than whisper-turbo.** `scripts/mlx-transcribe.py` runs diarized transcription through `mlx-community/VibeVoice-ASR-bf16`. Give long files generous wall-clock headroom: Phase 2 measured ~104s to transcribe a 30-second 2-speaker clip on a warm model (~3.5x realtime), plus a ~25s first load. Long-form support is ~60 min.
- **Diarization accuracy verified on real 2-speaker audio (Phase 2).** On the pyannote CallHome demo clip and two operator-supplied 2-speaker phone recordings (137s, 148s) VibeVoice separated both speakers correctly and consistently, with overlapping turns split between speakers rather than collapsed to one — the failure mode of the old mlx-whisper + pyannote greedy-overlap merge. The 148s speaker-alternating call transcribed end-to-end (~2x realtime). Not yet stress-tested on 3+ speakers or heavy crosstalk.
- **VibeVoice truncates on long single-speaker monologues.** A 137s clip that was ~130s of one speaker transcribed only its first 26s, then emitted a `[Speech]` placeholder for the rest. `_diarized_transcribe` detects the dropped span and returns a `warning` field pointing the caller to `transcribe_audio` (Parakeet handled the same file in full). Speaker-alternating audio is unaffected.
- **Apple-Silicon-only for the primary path.** The Docker fallback (`portal/modules/media/tools/whisper_mcp.py`) is faster-whisper `large-v3-turbo` with **no diarization** — speaker identification requires the host MLX server (:8924), and `transcribe_with_speakers` returns an error when that host is unreachable.
- **Speakers are model-inferred, not named.** Labels are `SPEAKER_00`, `SPEAKER_01`, … A `num_speakers` hint is accepted for API compatibility but VibeVoice infers speaker count itself.
- **OWUI tool-call timeout for long files.** OWUI's MCP tool-call ceiling can fire before a long file finishes. Raise `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` (set to 1800 in `.env.example`) or use the direct endpoint on port `8924`.

## Why

Single-pass diarized transcription (one model emits text + speaker + timestamps) removes the entire class of alignment bugs the previous mlx-whisper + pyannote greedy-overlap merge had (overlap collapse, speaker-count drift) and drops the `HF_TOKEN` gate, at the cost of a slower 9B forward pass. Sortformer + Parakeet remains the documented future two-stage upgrade if its mlx-audio Python API is confirmed.
