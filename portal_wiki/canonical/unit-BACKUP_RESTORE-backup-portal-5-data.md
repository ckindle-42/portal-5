---
id: unit-BACKUP_RESTORE-backup-portal-5-data
kind: why
title: "BACKUP_RESTORE \u2014 Backup Portal 5 data"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Backup Portal 5 data
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.823078
updated_at: 1783195000.823078
---

set -e

BACKUP_DIR="${BACKUP_DIR:-.}"
DATE=$(date +%Y%m%d-%H%M%S)

echo "Backing up Portal 6.0.0..."
