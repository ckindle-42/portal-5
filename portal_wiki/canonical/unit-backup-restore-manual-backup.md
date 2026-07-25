---
id: unit-backup-restore-manual-backup
kind: what
title: "BACKUP_RESTORE \u2014 Manual backup"
sources:
- type: doc
  path: docs/BACKUP_RESTORE.md
  commit: 05e42ec2
  section: Manual backup
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.5247529
updated_at: 1784946220.5247529
---

docker run --rm -v portal-5_open-webui-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/openwebui-backup-$(date +%Y%m%d).tar.gz /data
