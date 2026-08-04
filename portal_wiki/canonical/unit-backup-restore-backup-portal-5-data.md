---
id: unit-backup-restore-backup-portal-5-data
kind: what
title: "BACKUP_RESTORE \u2014 Backup Portal 5 data"
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
created_at: 1784946220.527649
updated_at: 1784946220.527649
---

The one-command entry point is `./launch.sh backup`, whose `_launch_backup` function orchestrates five artifacts in order: the `portal-5_open-webui-data` tarball, the `portal-5_grafana-data` tarball, a copy of `.env`, and the `config/` plus `imports/` trees. An optional positional argument overrides the output base directory, defaulting to `./backups`. Each volume tarball is produced through an alpine helper container that mounts the named volume directly, so the script does not depend on any single service being healthy.

## Why

Funneling every artifact through one command keeps the backup surface small enough to reason about and test. The script mounts volumes directly rather than asking each container to snapshot itself, which means backup succeeds even when individual services are down — the failure isolation that makes unattended runs trustworthy.
