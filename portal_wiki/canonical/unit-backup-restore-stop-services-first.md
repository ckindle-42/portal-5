---
id: unit-backup-restore-stop-services-first
kind: what
title: "BACKUP_RESTORE \u2014 Stop services first"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/util.sh
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.529363
updated_at: 1784946220.529363
---

Restoring data should happen while the stack is down, and `_launch_restore` enforces that internally by calling the same compose teardown the `down` case uses, passing the telegram and slack profiles so profiled containers are not orphaned. The standalone `./launch.sh down` command additionally stops the native macOS services such as the MLX generation MCPs and speech via launchctl or pkill. Backup, by contrast, mounts volumes directly and does not require the stack to be stopped first.

## Why

Volumes are safe to tar while services run, but writing restored files into a live database risks the running process overwriting them mid-restore. Restoring under a stopped stack is therefore built into the command itself rather than left to operator discipline, while the broader `down` stays available for full maintenance windows.
