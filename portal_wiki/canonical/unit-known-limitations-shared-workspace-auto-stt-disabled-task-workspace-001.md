---
id: unit-known-limitations-shared-workspace-auto-stt-disabled-task-workspace-001
kind: what
title: "KNOWN_LIMITATIONS \u2014 Shared Workspace + Auto-STT Disabled (TASK-WORKSPACE-001)"
sources:
- type: doc
  path: KNOWN_LIMITATIONS.md
  commit: 05e42ec2
  section: Shared Workspace + Auto-STT Disabled (TASK-WORKSPACE-001)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.674498
updated_at: 1784946220.674498
---

- **Voice-input via microphone is disabled.** `AUDIO_STT_ENGINE` is empty by default, which disables auto-transcription of both file uploads and microphone recordings. Re-enabling it re-enables auto-transcribe-on-upload. The global toggle is OWUI's only knob.
- **Existing MCPs not migrated to /workspace.** `mcp-documents`, `mcp-tts`, and `mcp-comfyui` still write to `${AI_OUTPUT_DIR}` flat. New MCPs use `/workspace/generated/<category>/`. Both layouts coexist; migration is opportunistic.
- **Permissions assume single-host deployment.** 0775 mode on workspace directories assumes operator-owned files and compatible Docker UIDs. Multi-tenant or hardened hosts need explicit UID mapping.
- **No retention policy.** `${AI_OUTPUT_DIR}` grows unbounded. `./launch.sh workspace-clean --age=Nd` is a planned but not yet implemented command.

---
