---
id: unit-BACKUP_RESTORE-mcp-data-if-exists
historical: true
kind: why
title: "BACKUP_RESTORE \u2014 MCP data (if exists)"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: MCP data (if exists)
confidence: high
tags:
- docs
- BACKUP_RESTORE

---

if docker volume ls -q | grep -q "portal-5_mcp-data"; then
    docker run --rm -v portal-5_mcp-data:/data -v ${BACKUP_DIR}:/backup \
        alpine tar czf /backup/mcp-${DATE}.tar.gz /data
fi

echo "Backup complete: ${DATE}"
ls -la ${BACKUP_DIR}/*-${DATE}.tar.gz
```
