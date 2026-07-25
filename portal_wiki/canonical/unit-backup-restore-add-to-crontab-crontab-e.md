---
id: unit-backup-restore-add-to-crontab-crontab-e
kind: what
title: "BACKUP_RESTORE \u2014 Add to crontab (crontab -e)"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: Add to crontab (crontab -e)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.532035
updated_at: 1784946220.532035
---

0 2 * * * cd /path/to/portal-5 && ./scripts/backup-portal.sh
```
