---
id: unit-HOWTO-voxtral-multilingual-transcription
kind: why
title: "HOWTO \u2014 Voxtral Multilingual Transcription"
sources:
- type: design
  path: docs/HOWTO.md
  section: Voxtral Multilingual Transcription
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8496552
updated_at: 1783195000.8496552
---


**What:** Mistral Voxtral-Mini-3B adds 8-language recognition (en, fr, de, es, it, pt, nl, ru) to the transcription stack. No diarization (single SPEAKER_00), but auto-language detection across supported languages.

**Pre-flight (one-time download, ~18.7 GB):**
```bash
./launch.sh pull-voxtral
