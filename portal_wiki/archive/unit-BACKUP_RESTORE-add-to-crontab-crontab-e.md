---
id: unit-BACKUP_RESTORE-add-to-crontab-crontab-e
kind: why
title: "BACKUP_RESTORE \u2014 Add to crontab (crontab -e)"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Add to crontab (crontab -e)
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.824466
updated_at: 1783195000.824466
---

0 2 * * * cd /path/to/portal-5 && ./scripts/backup-portal.sh
```
