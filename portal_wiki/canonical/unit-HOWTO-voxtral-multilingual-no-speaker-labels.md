---
id: unit-HOWTO-voxtral-multilingual-no-speaker-labels
kind: why
title: "HOWTO \u2014 Voxtral \u2014 multilingual, no speaker labels"
sources:
- type: design
  path: docs/HOWTO.md
  section: "Voxtral \u2014 multilingual, no speaker labels"
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.850112
updated_at: 1783195000.850112
---

curl -X POST http://localhost:8924/v1/audio/transcribe-with-speakers \
  -F "file=@meeting_fr.mp3" \
  -F "language=fr" | jq -r '.text'
```

Or via MCP tool in a pipeline:
```json
{"engine": "voxtral-mini-3b", "language": "de"}
```

**Trade-offs:**

| | whisper-large-v3-turbo (default) | voxtral-mini-3b |
|---|---|---|
| Languages | English-optimized | en/fr/de/es/it/pt/nl/ru |
| Speaker labels | Yes (pyannote diarization) | No |
| Model size | ~3 GB | ~18.7 GB |
| Requires HF_TOKEN | Yes (pyannote) | No |
| Use case | Multi-speaker English meetings | Multilingual single-speaker audio |
