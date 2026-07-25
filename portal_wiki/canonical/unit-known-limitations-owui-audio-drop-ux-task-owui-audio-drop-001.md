---
id: unit-known-limitations-owui-audio-drop-ux-task-owui-audio-drop-001
kind: what
title: "KNOWN_LIMITATIONS \u2014 OWUI Audio Drop UX (TASK-OWUI-AUDIO-DROP-001)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: OWUI Audio Drop UX (TASK-OWUI-AUDIO-DROP-001)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.675196
updated_at: 1784946220.675196
---

- **OWUI internal 60s tool-call ceiling.** Some OWUI builds enforce a hard internal timeout on tool execution that `AIOHTTP_CLIENT_TIMEOUT_TOOL_SERVER_DATA` does not affect (open-webui/open-webui#16902). When this fires, the tool completes server-side but the persona never sees the result. Use `scripts/transcribe_and_complete.sh` for files with wall time >60s.
- **WEBUI_SECRET_KEY rotation invalidates OAuth tokens.** If `.env` is regenerated and the secret key changes, all MCP OAuth tools need re-authentication.
- **Microphone voice input remains disabled.** Unchanged from TASK-WORKSPACE-001 trade-off.

---

---
