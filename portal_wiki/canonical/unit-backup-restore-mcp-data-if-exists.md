---
id: unit-backup-restore-mcp-data-if-exists
kind: what
title: "BACKUP_RESTORE \u2014 MCP data (if exists)"
sources:
- type: code
  path: .env.example
- type: code
  path: scripts/lib/backup.sh
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.528693
updated_at: 1784946220.528693
---

MCP-generated artifacts and user uploads live in the host workspace at `${AI_OUTPUT_DIR}`, defaulting to `${HOME}/AI_Output` per `.env.example`. The backup command does not include this directory, and it is not a Docker volume, so nothing in `scripts/lib/backup.sh` covers it. A manual archive of the workspace is the only path: create the tarball from the directory contents when the directory exists, and skip the step entirely when it does not.

```bash
AI_OUTPUT_DIR="${AI_OUTPUT_DIR:-$HOME/AI_Output}"
if [ -d "$AI_OUTPUT_DIR" ]; then
    tar czf "${BACKUP_DIR}/mcp-${DATE}.tar.gz" -C "$AI_OUTPUT_DIR" .
fi
```

## Why

The workspace is a host directory precisely so that all MCP servers and Open WebUI share the same files without container-local copies; the backup script predates or ignores that design. Because the directory is optional and can grow large, treating its archive as a guarded, separate step keeps the core backup fast while still making artifact retention possible.
