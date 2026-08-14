---
id: unit-backup-restore-2-configuration
kind: what
title: "BACKUP_RESTORE \u2014 2. Configuration"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.5305521
updated_at: 1784946220.5305521
---

The `config/` tree carries the operator-editable sources of truth: `portal.yaml` for workspaces and the MCP fleet, `backends.yaml` for the model catalog, and every persona file under `config/personas/`. `_launch_backup` copies the whole `config/` directory verbatim into the backup path instead of compressing it, so the layout survives byte-for-byte and can be diffed without extraction. Restore does not touch `config/`; after a restore the operator copies the saved directory back over the live tree by hand.

## Why

Configuration is cheap to store and expensive to reconstruct from memory, so the script copies it wholesale rather than pruning. Leaving config restoration out of the automated restore step is a deliberate boundary: config lives in version control too, so the backup copy is a convenience snapshot rather than the only authoritative source.
