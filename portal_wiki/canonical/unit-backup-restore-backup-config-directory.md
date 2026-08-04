---
id: unit-backup-restore-backup-config-directory
kind: what
title: "BACKUP_RESTORE \u2014 Backup config directory"
sources:
- type: code
  path: scripts/lib/backup.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.526219
updated_at: 1784946220.526219
---

`_launch_backup` archives the configuration directory by copying it rather than tarring it: `cp -r config/` and `cp -r imports/` place the trees inside the backup path as plain directories. Because every backup run creates a fresh timestamped parent directory, the config copy can never collide with a previous run's snapshot. The `.env` file, when present, is copied alongside as a flat file so the whole backup is self-contained.

## Why

A plain copy preserves the directory structure and lets an operator diff the saved config against the live tree without extracting anything. Timestamped parents make retention trivially understandable — each directory is one complete point-in-time state, and pruning is a single removal of the oldest directories.
