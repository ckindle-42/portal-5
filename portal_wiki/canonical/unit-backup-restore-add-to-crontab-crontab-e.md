---
id: unit-backup-restore-add-to-crontab-crontab-e
kind: what
title: "BACKUP_RESTORE \u2014 Add to crontab (crontab -e)"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/backup.sh
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.532035
updated_at: 1784946220.532035
---

No scheduler is shipped with the project; nothing in `launch.sh` or the scripts tree registers a recurring backup job. An operator who wants unattended snapshots must add the invocation to their own crontab. Because `_launch_backup` accepts an output directory as its second argument, a cron line can pin backups to a dedicated location rather than relying on the default `./backups`, and each run lands in its own timestamped subdirectory.

```bash
0 2 * * * cd /path/to/portal-5 && ./launch.sh backup ./backups
```

## Why

Backup cadence is an operational policy, not a platform invariant, so the code deliberately leaves scheduling to the operator. Wiring in a built-in cron entry would bake assumptions about uptime and rotation that differ per deployment; exposing a plain command the operator schedules keeps the platform portable while still offering the exact entry point a cron job needs.
