---
id: unit-BACKUP_RESTORE-config-excluding-env-for-security-back-that-up-man
historical: true
kind: why
title: "BACKUP_RESTORE \u2014 Config (excluding .env for security - back that up manually)"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Config (excluding .env for security - back that up manually)
confidence: high
tags:
- docs
- BACKUP_RESTORE

---

tar czf ${BACKUP_DIR}/config-${DATE}.tar.gz config/
