---
id: unit-backup-restore-mcp-data-if-exists
kind: what
title: "BACKUP_RESTORE \u2014 MCP data (if exists)"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: MCP data (if exists)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.528693
updated_at: 1784946220.528693
---

AI_OUTPUT_DIR="${AI_OUTPUT_DIR:-$HOME/AI_Output}"
if [ -d "$AI_OUTPUT_DIR" ]; then
    tar czf ${BACKUP_DIR}/mcp-${DATE}.tar.gz -C "$AI_OUTPUT_DIR" .
fi

echo "Backup complete: ${DATE}"
ls -la ${BACKUP_DIR}/*-${DATE}.tar.gz
```
