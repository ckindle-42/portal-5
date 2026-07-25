---
id: unit-backup-restore-complete-system-recovery
kind: what
title: "BACKUP_RESTORE \u2014 Complete System Recovery"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: Complete System Recovery
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.533063
updated_at: 1784946220.533063
---

1. **Reinstall Portal 5** (fresh clone or restore from git backup)
2. **Restore `.env`** (from your secure backup)
3. **Restore configuration**: `tar xzf config-backup-*.tar.gz`
4. **Restore Open WebUI**: `docker volume rm portal-5_open-webui-data` then restore
5. **Restart**: `./launch.sh up`
