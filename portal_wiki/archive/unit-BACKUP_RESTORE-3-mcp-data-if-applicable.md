---
id: unit-BACKUP_RESTORE-3-mcp-data-if-applicable
historical: true
kind: why
title: "BACKUP_RESTORE \u2014 3. MCP Data (if applicable)"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: 3. MCP Data (if applicable)
confidence: high
tags:
- docs
- BACKUP_RESTORE

---


```bash
docker run --rm -v portal-5_mcp-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/mcp-backup-$(date +%Y%m%d).tar.gz /data
```
