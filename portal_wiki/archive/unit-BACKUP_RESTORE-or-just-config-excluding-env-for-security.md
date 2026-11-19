---
id: unit-BACKUP_RESTORE-or-just-config-excluding-env-for-security
historical: true
kind: why
title: "BACKUP_RESTORE \u2014 Or just config (excluding .env for security)"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Or just config (excluding .env for security)
confidence: high
tags:
- docs
- BACKUP_RESTORE

---

tar czf config-backup-$(date +%Y%m%d).tar.gz config/
```
