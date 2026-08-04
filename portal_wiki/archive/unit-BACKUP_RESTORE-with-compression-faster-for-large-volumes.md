---
id: unit-BACKUP_RESTORE-with-compression-faster-for-large-volumes
kind: why
title: "BACKUP_RESTORE \u2014 With compression (faster for large volumes)"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: With compression (faster for large volumes)
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.8220952
updated_at: 1783195000.8220952
---

docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar -I 'gzip -9' -cf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```
