---
id: unit-BACKUP_RESTORE-add-to-crontab-crontab-e
historical: true
kind: why
title: "BACKUP_RESTORE \u2014 Add to crontab (crontab -e)"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Add to crontab (crontab -e)
confidence: high
tags:
- docs
- BACKUP_RESTORE

---

0 2 * * * cd /path/to/portal-5 && ./scripts/backup-portal.sh
```
