---
id: unit-BACKUP_RESTORE-config-excluding-env-for-security-back-that-up-man
kind: why
title: "BACKUP_RESTORE \u2014 Config (excluding .env for security - back that up manually)"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Config (excluding .env for security - back that up manually)
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.823543
updated_at: 1783195000.823543
---

tar czf ${BACKUP_DIR}/config-${DATE}.tar.gz config/
