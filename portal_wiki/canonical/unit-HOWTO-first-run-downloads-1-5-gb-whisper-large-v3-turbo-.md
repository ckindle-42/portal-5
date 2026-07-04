---
id: unit-HOWTO-first-run-downloads-1-5-gb-whisper-large-v3-turbo-
kind: why
title: "HOWTO \u2014 First run downloads ~1.5 GB whisper-large-v3-turbo + ~30 MB pyannote"
sources:
- type: design
  path: docs/HOWTO.md
  section: First run downloads ~1.5 GB whisper-large-v3-turbo + ~30 MB pyannote
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.848922
updated_at: 1783195000.848922
---

```

**Workflow A — Drop in chat (recommended for files <15 min):**

1. Open WebUI → select `Transcript Analyst` persona (Documents workspace)
2. Drag-drop an audio file (mp3, wav, m4a, ogg, flac) into the chat input
3. Type instructions, e.g., "transcribe with 2 speakers" or "summarize this meeting"
4. Hit submit
5. Persona detects the attachment, calls the transcription tool, displays the labeled transcript

The `transcriptanalyst` persona accepts:
- `"transcribe this"` — auto-detects speaker count
- `"transcribe with N speakers"` — passes `num_speakers=N` to constrain pyannote
- `"summarize this meeting"` — transcribe first, then produce a summary with decisions/action items
- `"make me a Word doc"` — transcribe, then chain to `create_word_document` for .docx output

**Workflow B — Long files (>15 min) or batch processing:**

For files where OWUI's tool timeout might bite (or for scripted use), call the HTTP endpoint directly:
```bash
curl -X POST http://localhost:8924/v1/audio/transcribe-with-speakers \
  -F "file=@long_meeting.mp3" \
  -F "num_speakers=3" | jq -r '.md_path'
