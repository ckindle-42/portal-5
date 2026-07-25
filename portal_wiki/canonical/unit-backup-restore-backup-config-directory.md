---
id: unit-backup-restore-backup-config-directory
kind: what
title: "BACKUP_RESTORE \u2014 Backup config directory"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: Backup config directory
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.526219
updated_at: 1784946220.526219
---

tar czf config-backup-$(date +%Y%m%d).tar.gz config/ .env
