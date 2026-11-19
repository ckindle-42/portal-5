---
id: unit-BACKUP_RESTORE-backup-config-directory
historical: true
kind: why
title: "BACKUP_RESTORE \u2014 Backup config directory"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Backup config directory
confidence: high
tags:
- docs
- BACKUP_RESTORE

---

tar czf config-backup-$(date +%Y%m%d).tar.gz config/ .env
