---
id: unit-BACKUP_RESTORE-complete-system-recovery
historical: true
kind: why
title: "BACKUP_RESTORE \u2014 Complete System Recovery"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Complete System Recovery
confidence: high
tags:
- docs
- BACKUP_RESTORE

---


1. **Reinstall Portal 5** (fresh clone or restore from git backup)
2. **Restore `.env`** (from your secure backup)
3. **Restore configuration**: `tar xzf config-backup-*.tar.gz`
4. **Restore Open WebUI**: `docker volume rm portal-5_open-webui-data` then restore
5. **Restart**: `./launch.sh up`
