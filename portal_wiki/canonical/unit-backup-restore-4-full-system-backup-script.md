---
id: unit-backup-restore-4-full-system-backup-script
kind: what
title: "BACKUP_RESTORE \u2014 4. Full System Backup Script"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.527282
updated_at: 1784946220.527282
---

The full-system backup is not a standalone script; it is `scripts/lib/backup.sh`, which `launch.sh` sources at startup and dispatches through the `backup` and `restore` case branches. `_launch_backup` builds a directory named `portal5_backup_<YYYYmmdd_HHMMSS>` under `./backups` by default, then produces the Open WebUI and Grafana tarballs, copies `.env`, `config/`, and `imports/`, and prints the matching restore command for that exact path. `_launch_restore` consumes that directory and reverses the volume and `.env` steps.

## Why

Keeping the backup logic in a sourced library instead of a self-contained script lets `launch.sh` reuse its `ENV_FILE` and `COMPOSE_DIR` plumbing without duplicating path resolution. The timestamped subdirectory names each run's output so a restore command can target precisely the snapshot it wants, and repeated runs never overwrite each other.
