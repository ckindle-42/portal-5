---
id: unit-backup-restore-daily-backup-with-cron
kind: what
title: "BACKUP_RESTORE \u2014 Daily Backup with Cron"
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
created_at: 1784946220.5316858
updated_at: 1784946220.5316858
---

A daily cadence is assembled by combining the operator's crontab with the `backup` command; there is no built-in daily job. The backup command is a one-shot, non-daemonizing run: it creates the timestamped directory, produces the artifacts, prints the restore hint, and exits. Running it from cron therefore works, but the cron environment must have access to the Docker socket and the `.env` file that `_launch_backup` sources at the top before it can mount the volumes.

## Why

A cron-triggered backup is only reliable if the command it invokes is idempotent and self-terminating, which the timestamped one-shot design guarantees. Each cron run yields an independent snapshot directory, so a failed or slow run never corrupts the previous night's backup.
