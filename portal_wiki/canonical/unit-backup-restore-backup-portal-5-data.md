---
id: unit-backup-restore-backup-portal-5-data
kind: what
title: "BACKUP_RESTORE \u2014 Backup Portal 5 data"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: Backup Portal 5 data
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.527649
updated_at: 1784946220.527649
---

set -e

BACKUP_DIR="${BACKUP_DIR:-.}"
DATE=$(date +%Y%m%d-%H%M%S)

echo "Backing up Portal 6.0.0..."
