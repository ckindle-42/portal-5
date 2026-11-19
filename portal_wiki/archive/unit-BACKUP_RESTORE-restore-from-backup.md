---
id: unit-BACKUP_RESTORE-restore-from-backup
historical: true
kind: why
title: "BACKUP_RESTORE \u2014 Restore from backup"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Restore from backup
confidence: high
tags:
- docs
- BACKUP_RESTORE

---

docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar xzf /backup/openwebui-backup-20260303.tar.gz -C /
