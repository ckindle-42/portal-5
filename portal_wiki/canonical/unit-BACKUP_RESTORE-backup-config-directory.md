---
id: unit-BACKUP_RESTORE-backup-config-directory
kind: why
title: "BACKUP_RESTORE \u2014 Backup config directory"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Backup config directory
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.82235
updated_at: 1783195000.82235
---

tar czf config-backup-$(date +%Y%m%d).tar.gz config/ .env
