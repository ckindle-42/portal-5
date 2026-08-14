---
id: unit-backup-restore-1-open-webui-data
kind: what
title: "BACKUP_RESTORE \u2014 1. Open WebUI Data"
sources:
- type: code
  path: scripts/lib/backup.sh
- type: code
  path: launch.sh
- type: code
  path: deploy/portal-5/docker-compose.yml
claims: []
confidence: high
tags:
- verified-v1
created_at: 1784946220.529026
updated_at: 1784946220.529026
---

Open WebUI stores users, chat history, settings, and workspace presets in the named `open-webui-data` volume, which the compose project under `deploy/portal-5` materializes as `portal-5_open-webui-data`. The `_launch_backup` function tars that volume into `openwebui-data.tar.gz` inside a fresh timestamped directory, and `_launch_restore` wipes the volume before extracting the tarball back in, so the current contents are overwritten by design. The two commands are the documented pair for moving this data around.

```bash
./launch.sh backup ./backups
./launch.sh restore ./backups/portal5_backup_20260301_120000
```

## Why

The Open WebUI database is the one piece of state the platform cannot regenerate: chat history and user accounts exist only in that volume. The restore path deliberately removes everything under the data mount before extracting, guaranteeing the recovered state matches the snapshot exactly rather than blending stale records with fresh ones.
