---
id: unit-HOWTO-diarized-transcription-speaker-labeled-transcripts
kind: why
title: "HOWTO \u2014 Diarized Transcription (Speaker-Labeled Transcripts)"
sources:
- type: code
  path: scripts/mlx-transcribe.py
- type: code
  path: scripts/lib/services.sh
last_generated_commit: 75c5054f791636f367b62a1776bcc9f631794766
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.848667
updated_at: 1783195000.848667
---

**What:** Drop an audio file in OWUI chat, get back a transcript with speaker labels (SPEAKER_00, SPEAKER_01, ...). Outputs JSON + Markdown to the shared workspace at `~/AI_Output/generated/transcripts/`.

**Pre-flight (one-time):**

1. Accept the gated pyannote models on HuggingFace (`pyannote/speaker-diarization-3.1` — the pipeline pulls the segmentation model internally)
2. Generate a read token at https://huggingface.co/settings/tokens
3. Add to `.env`: `HF_TOKEN=hf_...` — without it, `scripts/mlx-transcribe.py` refuses to load the diarization pipeline

**Start the service (Apple Silicon primary):**
```bash
./launch.sh start-transcribe
```
`_launch_start_transcribe` in `scripts/lib/services.sh` warns when `HF_TOKEN` is missing, then registers the server (port 8924, `MLX_TRANSCRIBE_PORT`) as a native service. The engine is `mlx-whisper` (large-v3-turbo) for transcription plus pyannote.audio 3.1 diarization on MPS; the `voxtral-mini-3b` engine is available for multilingual files. OWUI chats reach it through the workspace that grants `transcribe_with_speakers` (e.g. `auto-documents`), and the generated files are served as download URLs on port 8924.

## Why

Diarization is gated HuggingFace content, so the token requirement is enforced at load time rather than silently skipped — a transcript that claims speaker labels without pyannote would be wrong in a hard-to-notice way. Outputting both canonical JSON and a Markdown sidecar into the shared workspace means the transcript is immediately available to any other service, not just the chat thread that requested it.
