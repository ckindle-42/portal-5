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
updated_at: 1787934168.0
---

- **Two-stage, word-level merge.** `transcribe_with_speakers` = Parakeet-TDT-v3 transcript + Sortformer diarization (`mlx-community/diar_sortformer_4spk-v1-fp32`), merged by assigning each Parakeet word to the Sortformer speaker whose turn it overlaps. Fast: ~4s for a 2.5-min conversation on a warm model (Parakeet ~4s, Sortformer ~0.5s), plus a one-time model load.
- **4-speaker ceiling.** The Sortformer v1 model tops out at 4 concurrent speakers; a 5+-person recording will misassign. `num_speakers` only *caps* the count (folding over-segmented speakers into the nearest kept one), it cannot raise the ceiling.
- **Diarization verified on real 2-speaker audio.** The pyannote CallHome demo clip plus two operator-supplied 2-speaker phone recordings (137s monologue-heavy, 148s conversation): the conversation labelled correctly turn-by-turn end-to-end; the monologue collapsed to the one speaker as it should. Not stress-tested on 3+ speakers or heavy crosstalk. Speaker labels are arbitrary indices (`SPEAKER_00` = whoever speaks first), not identified people.
- **Boundary artefacts are smoothed, not eliminated.** A short speaker run wedged between two runs of the same other speaker is flipped back (`MLX_DIARIZE_MIN_TURN`, default 1.0s), and sentence-final punctuation is pinned to the previous word's speaker. A genuine <1s backchannel ("mm-hm", "okay") can therefore be absorbed into the other speaker's turn.
- **Long audio is chunked; limits are memory, not a hard cap.** On 64 GB Apple Silicon: Parakeet's single forward pass OOMs past ~40 min, so files over `MLX_PARAKEET_CHUNK_S` (120s) are transcribed in overlapping chunks (verified: 40 min → ~22s). Sortformer's full-context pass runs up to `MLX_DIARIZE_FULL_CONTEXT_MAX_S` (900s; clean to 20 min, swap-thrash by 25, OOM by 40), then switches to Sortformer's streaming pass (bounded memory, slightly noisier speaker identity). Above `MLX_DIARIZE_MAX_S` (10800s / 3 h) diarization is skipped.
- **Degrades to a transcript, never truncates.** If diarization is skipped or raises, the Parakeet transcript comes back as one speaker with a `warning`. JSON + Markdown are written to the workspace regardless, so a transcript survives an OWUI chat timeout.
- **OWUI wall-clock.** ~1 min transcription per hour of audio, plus seconds-to-~1 min diarization; a 2 h file is ~3–4 min. `WHISPER_PROXY_TIMEOUT` and `AIOHTTP_CLIENT_TIMEOUT*` both cap at 30 min.
- **Apple-Silicon-only for speaker labels.** The Docker fallback (`portal/modules/media/tools/whisper_mcp.py`) is faster-whisper `large-v3-turbo` with **no diarization**; `transcribe_with_speakers` returns an error (pointing at `transcribe_audio`) when the host MLX server (:8924) is unreachable.
- **OWUI tool-call timeout for long files.** OWUI's MCP tool-call ceiling can fire before a long file finishes. Raise `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` (set to 1800 in `.env.example`) or use the direct endpoint on port `8924`.

## Why

Splitting transcription (Parakeet) from diarization (Sortformer) instead of using one joint model means a diarization failure costs only the speaker labels, never the transcript — the single-pass model this replaced (VibeVoice-ASR 9B) stopped early on long single-speaker stretches and lost both text and labels for the remainder. It is also ~20× faster (VibeVoice ran ~2–3.5× real-time; this runs a few seconds regardless of length). Word-level assignment keeps a speaker change on a word boundary, and the smoothing pass suppresses the sub-second flicker that word-granularity would otherwise introduce at turn edges. Still no `HF_TOKEN` gate — both models are ungated on `mlx-community`.
