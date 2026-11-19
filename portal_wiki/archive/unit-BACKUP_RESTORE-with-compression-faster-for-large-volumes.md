---
id: unit-BACKUP_RESTORE-with-compression-faster-for-large-volumes
historical: true
kind: why
title: "BACKUP_RESTORE \u2014 With compression (faster for large volumes)"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: With compression (faster for large volumes)
confidence: high
tags:
- docs
- BACKUP_RESTORE

---

docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar -I 'gzip -9' -cf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```
