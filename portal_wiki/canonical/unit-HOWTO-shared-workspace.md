---
id: unit-HOWTO-shared-workspace
kind: why
title: "HOWTO \u2014 Shared Workspace"
sources:
- type: code
  path: portal/platform/mcp_host/workspace.py
claims: []
confidence: high
tags:
- HOWTO
- docs
- verified-v1
created_at: 1783195000.857887
updated_at: 1783195000.857887
---

**What:** A single host directory that all Portal 5 services read from and write to. Files dropped in OWUI chat, MCP-generated outputs, and host-native script outputs all live here, eliminating cross-service file-bridging friction.

**Where:** `AI_OUTPUT_DIR` in `.env` (default `~/AI_Output`). Containers see it mounted at `/workspace` with `WORKSPACE_DIR=/workspace` (docker-compose volumes), and Open WebUI's uploads bind-mount `${AI_OUTPUT_DIR}/uploads` to `/app/backend/data/uploads`. Path resolution lives in `portal/platform/mcp_host/workspace.py`: `WORKSPACE_DIR` → `AI_OUTPUT_DIR` → `/workspace` → `~/AI_Output`.

**Layout:**
```
~/AI_Output/
├── uploads/                ← Files dropped in OWUI chat
└── generated/
    ├── transcripts/        ← Diarized transcripts (mlx-transcribe, whisper)
    ├── documents/          ← Word/Excel/PowerPoint (documents MCP)
    ├── images/             ← MFLUX image outputs
    ├── videos/             ← Retained archival video-output category
    ├── music/              ← Music MCP outputs
    └── speech/             ← TTS outputs
```
`_VALID_CATEGORIES` in `workspace.py` also admits `models3d` (CAD render output).

**Initialize:**
```bash
./launch.sh workspace-init
```
(Run automatically on first `./launch.sh up` — the `up` case creates the tree.)

**Inspect:**
```bash
./launch.sh workspace-status     # File counts and sizes per category (cli workspace status)
./launch.sh workspace-show       # Resolved paths (host vs container)
```

**Use from MCP code (new modules):**
```python
from portal.platform.mcp_host import get_uploads_dir, get_generated_dir, resolve_upload_path
```

## Why

A single shared root with category subdirectories is the interface contract between services that otherwise have no shared filesystem understanding: a document MCP writes `generated/documents/`, the host user finds it in `~/AI_Output/`, and OWUI uploads land in `uploads/` for every service to read. Centralizing the paths in `mcp_host/workspace.py` means a future remap — a different mount point or drive — is one configuration change instead of a repo-wide search-and-replace.
