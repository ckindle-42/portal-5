---
id: unit-HOWTO-write-your-tool-s-output
kind: why
title: "HOWTO \u2014 Write your tool's output"
sources:
- type: design
  path: docs/HOWTO.md
  section: Write your tool's output
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8583539
updated_at: 1783195000.8583539
---

out = get_generated_dir("transcripts") / f"transcript_{uid}.json"
out.write_text(json_payload)
```

**Drop-and-process workflow:** when a user drags an audio/document/image into OWUI chat, the file lands at `~/AI_Output/uploads/<file_id>`. The persona consuming the message can call any MCP tool and pass the file path; the MCP container sees the same file at `/workspace/uploads/<file_id>`.

**Auto-STT note:** Open WebUI's auto-transcription (`AUDIO_STT_ENGINE`) is disabled. Audio file uploads in chat stay as attachments — personas process them via MCP tools (e.g., `transcribe_with_speakers`). **Side effect:** voice-input via the OWUI microphone button does not transcribe. To re-enable voice-input only, see KNOWN_LIMITATIONS.md.

---
