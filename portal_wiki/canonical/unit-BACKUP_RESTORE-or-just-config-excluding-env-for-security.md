---
id: unit-BACKUP_RESTORE-or-just-config-excluding-env-for-security
kind: why
title: "BACKUP_RESTORE \u2014 Or just config (excluding .env for security)"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Or just config (excluding .env for security)
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.822586
updated_at: 1783195000.822586
---

tar czf config-backup-$(date +%Y%m%d).tar.gz config/
```
