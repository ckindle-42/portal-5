---
id: unit-backup-restore-cleanup-old-backups-run-daily
kind: what
title: "BACKUP_RESTORE \u2014 Cleanup old backups (run daily)"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: Cleanup old backups (run daily)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.532727
updated_at: 1784946220.532727
---

find . -name "openwebui-*.tar.gz" -mtime +7 -delete
find . -name "config-*.tar.gz" -mtime +30 -delete
```
