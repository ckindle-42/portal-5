---
id: unit-BACKUP_RESTORE-open-webui-data
kind: why
title: "BACKUP_RESTORE \u2014 Open WebUI data"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Open WebUI data
last_generated_commit: ''
confidence: high
tags:
- docs
- BACKUP_RESTORE
created_at: 1783195000.823314
updated_at: 1783195000.823314
---

docker run --rm -v portal-5_open-webui-data:/data -v ${BACKUP_DIR}:/backup \
    alpine tar czf /backup/openwebui-${DATE}.tar.gz /data
