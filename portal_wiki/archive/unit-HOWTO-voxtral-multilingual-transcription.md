---
id: unit-HOWTO-voxtral-multilingual-transcription
historical: true
kind: why
title: "HOWTO \u2014 Voxtral Multilingual Transcription"
sources:
- type: design
  path: docs/HOWTO.md
  section: Voxtral Multilingual Transcription
confidence: high
tags:
- docs
- HOWTO

---


**What:** Mistral Voxtral-Mini-3B adds 8-language recognition (en, fr, de, es, it, pt, nl, ru) to the transcription stack. No diarization (single SPEAKER_00), but auto-language detection across supported languages.

**Pre-flight (one-time download, ~18.7 GB):**
```bash
./launch.sh pull-voxtral
