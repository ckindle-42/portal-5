---
id: unit-claude-11-shared-workspace-is-the-only-path-for-user-file
kind: why
title: "CLAUDE.md \u2014 11 \u2014 Shared Workspace Is The Only Path For User Files"
sources:
- type: design
  path: CLAUDE.md
  section: "11 \u2014 Shared Workspace Is The Only Path For User Files"
last_generated_commit: ''
confidence: high
tags:
- claude
- architecture
- law
created_at: 1783195000.809032
updated_at: 1783195000.809032
---


User-uploaded files and cross-MCP artifacts live at `${AI_OUTPUT_DIR}` (default `~/AI_Output/`), mounted into containers at `/workspace`. Never write user-facing artifacts to a container-local volume that other services cannot see.

- Reads of user uploads: `portal_mcp.core.resolve_upload_path(file_id)` or `/workspace/uploads/<id>`.
- Writes of generated artifacts: `portal_mcp.core.get_generated_dir(category)` or `/workspace/generated/<category>/`.
- Categories: `transcripts`, `documents`, `images`, `videos`, `music`, `speech`. Add a new category by editing `_VALID_CATEGORIES` in `portal_mcp/core/workspace.py` (this is the source of truth — `launch.sh workspace-init` and the docker-compose mounts derive from this list).
- New Docker MCPs that touch user files: add `${AI_OUTPUT_DIR:-${HOME}/AI_Output}:/workspace` to the volumes block and `WORKSPACE_DIR=/workspace` to the environment block.
- `AUDIO_STT_ENGINE` is intentionally empty in the OWUI config — auto-transcription is disabled so audio uploads remain accessible to personas. Do not re-enable it without a migration plan for affected workflows.

---
