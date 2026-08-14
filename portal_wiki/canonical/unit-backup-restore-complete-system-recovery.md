---
id: unit-backup-restore-complete-system-recovery
kind: what
title: "BACKUP_RESTORE \u2014 Complete System Recovery"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.533063
updated_at: 1784946220.533063
---

Full recovery is: reinstall the platform, restore `.env` so secrets and routing config are present, then run `./launch.sh restore <backup-path>`. The restore command stops the running stack itself, wipes and repopulates the Open WebUI and Grafana volumes, and copies `.env` back into place. The saved `config/` and `imports/` trees must be copied over manually because `_launch_restore` does not touch them, then `./launch.sh up` recreates all containers against the restored state.

## Why

The restore path deliberately limits itself to state that cannot be regenerated — the databases and the secrets file — while leaving versioned config to the operator's own copy. That split keeps the destructive command minimal and predictable; a restore that silently overwrote live config would merge an operator's post-backup tuning with stale files.
