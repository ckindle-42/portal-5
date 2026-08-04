---
id: unit-BACKUP_RESTORE-3-mcp-data-if-applicable
kind: why
title: "BACKUP_RESTORE \u2014 3. MCP Data (if applicable)"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: 3. MCP Data (if applicable)
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.822835
updated_at: 1783195000.822835
---


```bash
docker run --rm -v portal-5_mcp-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/mcp-backup-$(date +%Y%m%d).tar.gz /data
```
