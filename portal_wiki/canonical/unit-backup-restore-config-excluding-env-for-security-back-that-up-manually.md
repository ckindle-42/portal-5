---
id: unit-backup-restore-config-excluding-env-for-security-back-that-up-manually
kind: what
title: "BACKUP_RESTORE \u2014 Config (excluding .env for security - back that up manually)"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: Config (excluding .env for security - back that up manually)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.528335
updated_at: 1784946220.528335
---

tar czf ${BACKUP_DIR}/config-${DATE}.tar.gz config/
