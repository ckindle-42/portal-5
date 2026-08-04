---
id: unit-backup-restore-3-mcp-data-if-applicable
kind: what
title: "BACKUP_RESTORE \u2014 3. MCP Data (if applicable)"
sources:
- type: code
  path: .env.example
- type: code
  path: scripts/lib/backup.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.526913
updated_at: 1784946220.526913
---

MCP servers read uploads from `${AI_OUTPUT_DIR}/uploads` and write generated artifacts under `${AI_OUTPUT_DIR}/generated/<category>`, per the workspace layout defined in `.env.example` and mounted into containers at `/workspace`. That host directory is not a Docker volume and is absent from the artifact sequence in `_launch_backup`, so `./launch.sh backup` does not cover it. The only way to capture it is a manual archive of the workspace directory.

```bash
tar czf mcp-backup-$(date +%Y%m%d).tar.gz -C "${AI_OUTPUT_DIR:-$HOME/AI_Output}" .
```

## Why

User-uploaded files and generated documents are host state, not container volumes, which is exactly why the shared-workspace rule exists; the backup script was written for Docker volumes and never taught about the host path. Until the script grows an explicit step for it, operators who value those files must schedule their own archive of the workspace.
