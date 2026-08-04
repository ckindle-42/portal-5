---
id: unit-backup-restore-cleanup-old-backups-run-daily
kind: what
title: "BACKUP_RESTORE \u2014 Cleanup old backups (run daily)"
sources:
- type: code
  path: launch.sh
- type: code
  path: scripts/lib/backup.sh
last_generated_commit: 2f35b5ad508cd284e75ad0735ab7db02961001dd
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.532727
updated_at: 1784946220.532727
---

Nothing in the repo runs a daily cleanup of backup directories. The `clean` case tears down the stack and removes only the Open WebUI data volume, explicitly preserving the Ollama model volume; it does not touch anything under `./backups`. Any age-based pruning of snapshots, such as deleting tarballs older than a week, must be scheduled by the operator as a separate job operating on the backup directory.

## Why

The name `clean` means reset the Open WebUI database, not reclaim backup disk, and conflating the two would destroy recovery points during routine maintenance. Keeping snapshot pruning fully separate from stack cleanup means an operator who runs `./launch.sh clean` can be confident their restore history is untouched.
