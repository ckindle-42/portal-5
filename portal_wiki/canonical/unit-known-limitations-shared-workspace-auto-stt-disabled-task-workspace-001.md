---
id: unit-known-limitations-shared-workspace-auto-stt-disabled-task-workspace-001
kind: what
title: "KNOWN_LIMITATIONS \u2014 Shared Workspace + Auto-STT Disabled (TASK-WORKSPACE-001)"
sources:
- type: code
  path: .env.example
- type: code
  path: deploy/portal-5/docker-compose.yml
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/services.sh
last_generated_commit: a81c5e73569f981ecedb0d95b088563fcce651ed
claims: []
confidence: high
tags:
- docs
- verified-v1
created_at: 1784946220.674498
updated_at: 1784946220.674498
---

- **Voice-input via microphone is disabled.** `OWUI_AUDIO_STT_ENGINE` is empty in `.env.example`, and `deploy/portal-5/docker-compose.yml` passes it through as `AUDIO_STT_ENGINE` to Open WebUI, disabling auto-transcription of both file uploads and microphone recordings. Re-enabling it re-enables auto-transcribe-on-upload. The global toggle is OWUI's only knob.
- **Existing MCPs not migrated to /workspace.** `mcp-documents` and `mcp-tts` in `deploy/portal-5/docker-compose.yml` write to `${AI_OUTPUT_DIR}` via `OUTPUT_DIR=/app/data/generated` (mounted flat), while newer MCPs (e.g. `mcp-whisper`) use `WORKSPACE_DIR=/workspace` with `/workspace/generated/<category>/` subpaths. Both layouts coexist; migration is opportunistic.
- **Permissions assume single-host deployment.** `launch.sh` and `scripts/lib/services.sh` apply `chmod -R 0775` to the workspace tree, which assumes operator-owned files and compatible Docker UIDs. Multi-tenant or hardened hosts need explicit UID mapping.
- **No retention policy.** `${AI_OUTPUT_DIR}` grows unbounded; `./launch.sh workspace-clean --age=Nd` is a planned but not yet implemented command.

## Why

The shared-workspace contract is the single path for user files, but the migration from flat `${AI_OUTPUT_DIR}` writes to the `/workspace/generated/<category>/` layout is still incomplete, so both layouts coexist and any code must handle both. Auto-STT is intentionally off to keep audio uploads accessible to personas, and permissive permissions are accepted because the deployment is single-host — each constraint is a deliberate, documented trade-off rather than an accident.
