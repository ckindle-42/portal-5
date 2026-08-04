---
id: unit-HOWTO-when-chat-drop-still-doesn-t-work-the-runner-scrip
kind: why
title: "HOWTO \u2014 When chat-drop still doesn't work \u2014 the runner script"
sources:
- type: design
  path: docs/HOWTO.md
  section: "When chat-drop still doesn't work \u2014 the runner script"
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.8505778
updated_at: 1783195000.8505778
---


Some OWUI builds enforce an additional internal 60s ceiling on tool calls that no env var lifts (open-webui#16902). If you hit that on a long file, use the manual runner:

```bash
./scripts/transcribe_and_complete.sh meeting.m4a --speakers 2
```

This script transcribes via curl, sends the transcript to the persona via OWUI's API, the persona renders the .docx via its `create_word_document` tool, then reviews its own output. Final .docx + transcript artifacts land next to your source audio. Same persona, same outputs, just orchestrated by the script instead of a chat session.

---
