---
id: unit-backup-restore-restore-from-backup
kind: what
title: "BACKUP_RESTORE \u2014 Restore from backup"
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
created_at: 1784946220.529736
updated_at: 1784946220.529736
---

Restoring is `./launch.sh restore <backup-path>`, a deliberately interactive command: `_launch_restore` requires a directory argument, prints a warning that current data will be overwritten, and waits for an explicit `y` or `Y` confirmation before touching anything. It then stops the stack with the telegram and slack profiles, restores the Open WebUI and Grafana tarballs by clearing each volume and extracting, and copies `.env` back into place.

## Why

The confirm prompt exists because the restore path clears the destination volume before extraction — an irreversible operation that a mistaken invocation would otherwise perform silently. Making the destructive step require a typed confirmation matches the weight of the action, and the argument check rejects typos that name a nonexistent snapshot.
