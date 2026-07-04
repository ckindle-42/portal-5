---
id: unit-HOWTO-shared-workspace
kind: why
title: "HOWTO \u2014 Shared Workspace"
sources:
- type: design
  path: docs/HOWTO.md
  section: Shared Workspace
last_generated_commit: ''
confidence: high
tags:
- docs
- HOWTO
created_at: 1783195000.857887
updated_at: 1783195000.857887
---


**What:** A single host directory that all Portal 5 services read from and write to. Files dropped in OWUI chat, MCP-generated outputs, and host-native script outputs all live here. Eliminates cross-service file-bridging friction.

**Where:** `${AI_OUTPUT_DIR}` on the host (default `~/AI_Output/`). Mounted into containers at `/workspace`. OWUI's uploads directory bind-mounts to `${AI_OUTPUT_DIR}/uploads`.

**Layout:**
```
~/AI_Output/
├── uploads/                ← Files dropped in OWUI chat
└── generated/
    ├── transcripts/        ← Diarized transcripts (mlx-transcribe, whisper)
    ├── documents/          ← Word/Excel/PowerPoint (documents MCP)
    ├── images/             ← ComfyUI outputs
    ├── videos/             ← Video MCP outputs
    ├── music/              ← Music MCP outputs
    └── speech/             ← TTS outputs
```

**Initialize:**
```bash
./launch.sh workspace-init
```
(Run automatically on first `./launch.sh up`.)

**Inspect:**
```bash
./launch.sh workspace-status     # File counts and sizes per category
./launch.sh workspace-show       # Resolved paths (host vs container)
```

**Use from MCP code (new modules):**
```python
from portal_mcp.core import get_uploads_dir, get_generated_dir, resolve_upload_path
