---
id: unit-BACKUP_RESTORE-cleanup-old-backups-run-daily
kind: why
title: "BACKUP_RESTORE \u2014 Cleanup old backups (run daily)"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Cleanup old backups (run daily)
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.824933
updated_at: 1783195000.824933
---

find . -name "openwebui-*.tar.gz" -mtime +7 -delete
find . -name "config-*.tar.gz" -mtime +30 -delete
```
