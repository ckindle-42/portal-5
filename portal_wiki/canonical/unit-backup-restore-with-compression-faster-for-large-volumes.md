---
id: unit-backup-restore-with-compression-faster-for-large-volumes
kind: what
title: "BACKUP_RESTORE \u2014 With compression (faster for large volumes)"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: With compression (faster for large volumes)
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.525281
updated_at: 1784946220.525281
---

docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar -I 'gzip -9' -cf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
```
