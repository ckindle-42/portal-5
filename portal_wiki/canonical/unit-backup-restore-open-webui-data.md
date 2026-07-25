---
id: unit-backup-restore-open-webui-data
kind: what
title: "BACKUP_RESTORE \u2014 Open WebUI data"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: Open WebUI data
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5280042
updated_at: 1784946220.5280042
---

docker run --rm -v portal-5_open-webui-data:/data -v ${BACKUP_DIR}:/backup \
    alpine tar czf /backup/openwebui-${DATE}.tar.gz /data
