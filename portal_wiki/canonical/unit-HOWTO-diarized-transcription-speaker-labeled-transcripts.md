---
id: unit-HOWTO-diarized-transcription-speaker-labeled-transcripts
kind: why
title: "HOWTO \u2014 Diarized Transcription (Speaker-Labeled Transcripts)"
sources:
- type: design
  path: docs/HOWTO.md
  section: Diarized Transcription (Speaker-Labeled Transcripts)
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.848667
updated_at: 1783195000.848667
---


**What:** Drop an audio file in OWUI chat, get back a transcript with speaker labels (SPEAKER_00, SPEAKER_01, ...). Outputs JSON + Markdown to the shared workspace at `~/AI_Output/generated/transcripts/`.

**Pre-flight (one-time):**

1. Visit `https://huggingface.co/pyannote/segmentation-3.0` — accept user conditions
2. Visit `https://huggingface.co/pyannote/speaker-diarization-3.1` — accept user conditions
3. Generate read token at `https://huggingface.co/settings/tokens`
4. Add to `.env`: `HF_TOKEN=hf_...`

**Start the service (Apple Silicon primary):**
```bash
./launch.sh start-transcribe
