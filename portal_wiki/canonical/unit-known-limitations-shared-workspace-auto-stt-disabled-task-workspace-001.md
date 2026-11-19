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
claims: []
confidence: high
tags:
- docs
- verified-v1

---

- **Voice-input via microphone runs on Portal's ASR, not OWUI's local engine.** `OWUI_AUDIO_STT_ENGINE=openai` in `.env.example` (passed through by `deploy/portal-5/docker-compose.yml`) sends OWUI's mic and upload transcription to the MLX transcribe server on `host.docker.internal:8924/v1`, which replaces the in-container CPU faster-whisper "base". An empty value is not "off" — it selects that local engine. The ASR weights must be fetched once with `./launch.sh pull-asr-models` (the services run `HF_HUB_OFFLINE=1`); until then OWUI's STT call returns a `503` naming that command and everything else in OWUI keeps working. The global toggle is OWUI's only knob.
- **Existing MCPs not migrated to /workspace.** `mcp-documents` and `mcp-tts` in `deploy/portal-5/docker-compose.yml` write to `${AI_OUTPUT_DIR}` via `OUTPUT_DIR=/app/data/generated` (mounted flat), while newer MCPs (e.g. `mcp-whisper`) use `WORKSPACE_DIR=/workspace` with `/workspace/generated/<category>/` subpaths. Both layouts coexist; migration is opportunistic.
- **Permissions assume single-host deployment.** `launch.sh` and `scripts/lib/services.sh` apply `chmod -R 0775` to the workspace tree, which assumes operator-owned files and compatible Docker UIDs. Multi-tenant or hardened hosts need explicit UID mapping.
- **No retention policy.** `${AI_OUTPUT_DIR}` grows unbounded; `./launch.sh workspace-clean --age=Nd` is a planned but not yet implemented command.

## Why

The shared-workspace contract is the single path for user files, but the migration from flat `${AI_OUTPUT_DIR}` writes to the `/workspace/generated/<category>/` layout is still incomplete, so both layouts coexist and any code must handle both. Voice input is wired to Portal's own ASR rather than kept in-container: the MLX Parakeet server is the engine the transcription tools already use, so OWUI and the tools now share one engine and one model, and the only prerequisite is the one-time weight fetch. Permissive permissions are accepted because the deployment is single-host — each constraint is a deliberate, documented trade-off rather than an accident.
