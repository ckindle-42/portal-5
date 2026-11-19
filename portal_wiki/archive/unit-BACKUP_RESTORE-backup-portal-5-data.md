---
id: unit-BACKUP_RESTORE-backup-portal-5-data
historical: true
kind: why
title: "BACKUP_RESTORE \u2014 Backup Portal 5 data"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Backup Portal 5 data
confidence: high
tags:
- docs
- BACKUP_RESTORE

---

set -e

BACKUP_DIR="${BACKUP_DIR:-.}"
DATE=$(date +%Y%m%d-%H%M%S)

echo "Backing up Portal 6.0.0..."
