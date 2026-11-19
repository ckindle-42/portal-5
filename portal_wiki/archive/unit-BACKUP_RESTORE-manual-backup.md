---
id: unit-BACKUP_RESTORE-manual-backup
historical: true
kind: why
title: "BACKUP_RESTORE \u2014 Manual backup"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Manual backup
confidence: high
tags:
- docs
- BACKUP_RESTORE

---

docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
