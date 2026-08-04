---
id: unit-BACKUP_RESTORE-complete-system-recovery
kind: why
title: "BACKUP_RESTORE \u2014 Complete System Recovery"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Complete System Recovery
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.825173
updated_at: 1783195000.825173
---


1. **Reinstall Portal 5** (fresh clone or restore from git backup)
2. **Restore `.env`** (from your secure backup)
3. **Restore configuration**: `tar xzf config-backup-*.tar.gz`
4. **Restore Open WebUI**: `docker volume rm portal-5_open-webui-data` then restore
5. **Restart**: `./launch.sh up`
