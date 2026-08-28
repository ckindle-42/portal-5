---
id: unit-HOWTO-diarized-transcription-speaker-labeled-transcripts
kind: why
title: "HOWTO \u2014 Diarized Transcription (Speaker-Labeled Transcripts)"
sources:
- type: code
  path: scripts/mlx-transcribe.py
- type: code
  path: scripts/lib/services.sh
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.848667
updated_at: 1787931459.0
---

**What:** Drop an audio file in an OWUI chat that grants `transcribe_with_speakers` (e.g. `auto-audio`, `auto-documents`), ask "who said what", and get back a transcript with speaker labels (`SPEAKER_00`, `SPEAKER_01`, …). A single-speaker recording simply comes back as one speaker — you don't have to know in advance. Outputs JSON + Markdown to the shared workspace at `~/AI_Output/generated/transcripts/`, served as download URLs on port 8924.

**Pre-flight:** none. No HuggingFace token, no gated models.

**Start the service (Apple Silicon):**
```bash
./launch.sh start-transcribe
```
`_launch_start_transcribe` in `scripts/lib/services.sh` pre-downloads Parakeet-TDT-v3 and the Sortformer diarizer (`mlx-community/diar_sortformer_4spk-v1-fp32`), then registers the server (port 8924, `MLX_TRANSCRIBE_PORT`) as a native service. Under launchd it runs with `HF_HUB_OFFLINE=1` and serves strictly from the warmed cache.

**How it works:** Parakeet produces the full transcript with a timestamp on every word. Sortformer produces speaker turns ("speaker 1 from 0.0–12.4s, speaker 2 from 12.4–18.0s, …"). The server assigns each word to the speaker whose turn it overlaps, groups consecutive same-speaker words into turns, and smooths sub-second flicker at the boundaries. Up to 4 speakers. `num_speakers` optionally caps the count.

## Why

Two models, not one. If the diarizer is skipped (file past `MLX_DIARIZE_MAX_S`) or fails, you still get the complete Parakeet transcript as one speaker with a `warning` — a joint transcribe-and-diarize model that stops early loses the text too. Word-level assignment keeps a speaker change on a word boundary instead of mid-word. Outputting both canonical JSON and a Markdown sidecar into the shared workspace means the transcript is immediately available to any other service, not just the chat thread that requested it.
