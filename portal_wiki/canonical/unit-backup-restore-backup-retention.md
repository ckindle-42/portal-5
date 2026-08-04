---
id: unit-backup-restore-backup-retention
kind: what
title: "BACKUP_RESTORE \u2014 Backup Retention"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.532368
updated_at: 1784946220.532368
---

There is no retention policy implemented anywhere in the codebase: `_launch_backup` never deletes older backups, and no other script sweeps the `./backups` directory. Every run simply adds another `portal5_backup_<timestamp>` directory, so the set grows monotonically until the operator prunes it. The daily-for-a-week, weekly-for-a-month, monthly-for-a-year ladder suggested by the old guide is advisory documentation, not enforced behavior.

## Why

Retention is a capacity decision that depends on disk budget and restore SLAs, so it was left out of the automation rather than hard-coded. Making the absence explicit prevents an operator from believing old snapshots are being rotated automatically when in fact every run is retained indefinitely until someone deletes it.
