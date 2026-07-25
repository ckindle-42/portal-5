---
id: unit-backup-restore-3-mcp-data-if-applicable
kind: what
title: "BACKUP_RESTORE \u2014 3. MCP Data (if applicable)"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: 3. MCP Data (if applicable)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.526913
updated_at: 1784946220.526913
---

```bash
tar czf mcp-backup-$(date +%Y%m%d).tar.gz -C "${AI_OUTPUT_DIR:-$HOME/AI_Output}" .
```
