---
id: unit-BACKUP_RESTORE-open-webui-data
historical: true
kind: why
title: "BACKUP_RESTORE \u2014 Open WebUI data"
sources:
- type: design
  path: docs/BACKUP_RESTORE.md
  section: Open WebUI data
confidence: high
tags:
- docs
- BACKUP_RESTORE

---

docker run --rm -v portal-5_open-webui-data:/data -v ${BACKUP_DIR}:/backup \
    alpine tar czf /backup/openwebui-${DATE}.tar.gz /data
